"""
Asynchronous transcription + analysis pipeline.

Rather than blocking the HTTP request (and risking gateway timeouts on large
files), ``POST /process`` creates a ``ProcessingJob`` row and hands the work to
a small in-process thread pool. The row is updated as the job moves through its
stages, which lets the client either poll ``GET /jobs/{id}`` or subscribe to the
live ``GET /jobs/{id}/stream`` SSE feed.

Why in-process threads instead of Celery/Dramatiq: transcription runs against a
Whisper model that is loaded once, in this process, as a singleton. A separate
broker-backed worker (Redis/RabbitMQ) could not share that loaded model and
would add heavy infra for a SQLite-backed app. A bounded ``ThreadPoolExecutor``
keeps the design dependency-free while still freeing the request thread and
capping concurrent, memory-hungry transcriptions. The DB row is the durable
source of truth, so the design can later be swapped for Celery without changing
the API contract.
"""
import os
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Meeting, ActionItem, Decision, ProcessingJob
from .whisper_service import whisper_service
from .ai_service import ai_service
from .vector_service import vector_service

logger = logging.getLogger(__name__)

# One shared pool for the process lifetime. max_workers caps how many
# transcriptions run at once (each is CPU/GPU and memory heavy).
_executor = ThreadPoolExecutor(
    max_workers=max(1, settings.MAX_CONCURRENT_JOBS),
    thread_name_prefix="job-worker",
)

# Terminal states after which no further updates are emitted.
TERMINAL_STATUSES = {"completed", "failed"}


# --------------------------------------------------------------------------- #
# Analysis helpers (shared with the synchronous endpoints so the mapping from
# the AI analysis dict onto the ORM models lives in exactly one place).
# --------------------------------------------------------------------------- #

def apply_summary(meeting: Meeting, analysis: Dict[str, Any]) -> None:
    """Write summary, risks, follow-ups and sentiment onto a Meeting."""
    meeting.summary_executive = analysis.get("summary_executive")
    meeting.summary_detailed = analysis.get("summary_detailed")
    meeting.summary_highlights = analysis.get("summary_highlights")
    meeting.risks = "\n".join(analysis.get("risks", [])) if analysis.get("risks") else None
    meeting.follow_ups = "\n".join(analysis.get("follow_ups", [])) if analysis.get("follow_ups") else None

    sentiment = analysis.get("sentiment", {})
    meeting.sentiment_positive = sentiment.get("positive", 0.0)
    meeting.sentiment_neutral = sentiment.get("neutral", 0.0)
    meeting.sentiment_negative = sentiment.get("negative", 0.0)


def apply_actions(db: Session, meeting: Meeting, analysis: Dict[str, Any]) -> None:
    """Replace a meeting's action items and decisions from the AI analysis."""
    db.query(ActionItem).filter(ActionItem.meeting_id == meeting.id).delete()
    db.query(Decision).filter(Decision.meeting_id == meeting.id).delete()

    for item in analysis.get("action_items", []):
        db.add(ActionItem(
            meeting_id=meeting.id,
            task=item.get("task"),
            owner=item.get("owner", "Unassigned"),
            deadline=item.get("deadline"),
            priority=item.get("priority", "Medium"),
            status=item.get("status", "Pending"),
        ))

    for dec_text in analysis.get("decisions", []):
        db.add(Decision(meeting_id=meeting.id, decision_text=dec_text))


# --------------------------------------------------------------------------- #
# Job lifecycle
# --------------------------------------------------------------------------- #

def create_and_start(db: Session, user_id: int, filename: str, title: str) -> ProcessingJob:
    """Persist a queued job and schedule it on the background pool."""
    job = ProcessingJob(
        id=uuid4().hex,
        user_id=user_id,
        filename=filename,
        title=title,
        status="queued",
        stage="Queued",
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    _executor.submit(_process, job.id)
    return job


def get_job(db: Session, task_id: str, user_id: int) -> Optional[ProcessingJob]:
    return (
        db.query(ProcessingJob)
        .filter(ProcessingJob.id == task_id, ProcessingJob.user_id == user_id)
        .first()
    )


def serialize(job: ProcessingJob) -> Dict[str, Any]:
    """Shape a job for the API/SSE payload (maps ``id`` -> ``task_id``)."""
    return {
        "task_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "meeting_id": job.meeting_id,
        "error": job.error,
        "title": job.title,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _set(db: Session, job: ProcessingJob, **fields: Any) -> None:
    """Update job fields and commit so pollers and the SSE stream see progress."""
    for key, value in fields.items():
        setattr(job, key, value)
    db.commit()


def _process(task_id: str) -> None:
    """Run the full pipeline for one job in its own DB session/thread."""
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, task_id)
        if job is None:
            logger.error("Processing job %s vanished before it could start.", task_id)
            return

        file_path = os.path.join(settings.UPLOAD_DIR, job.filename)
        if not os.path.exists(file_path):
            _set(db, job, status="failed", stage="Failed", error="Uploaded file not found.")
            return

        # 1. Transcription (the slow, timeout-prone step).
        _set(db, job, status="transcribing", stage="Transcribing audio", progress=15)
        transcript = whisper_service.transcribe_audio(file_path)

        # 2. Persist the meeting record and link it to the job.
        meeting = Meeting(
            user_id=job.user_id,
            title=job.title,
            filename=job.filename,
            transcript=transcript,
            sentiment_positive=0.0,
            sentiment_neutral=0.0,
            sentiment_negative=0.0,
        )
        db.add(meeting)
        db.commit()
        db.refresh(meeting)
        _set(db, job, meeting_id=meeting.id, stage="Indexing transcript", progress=45)

        # Index for RAG chat. Non-fatal: a failure here shouldn't sink the job.
        try:
            vector_service.index_meeting(meeting.id, transcript)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Indexing transcript for meeting %s failed: %s", meeting.id, exc)

        # 3. Analyse once, reuse for both summary and action extraction
        #    (the old synchronous flow called the LLM twice for this).
        _set(db, job, status="summarizing", stage="Generating summary", progress=60)
        analysis = ai_service.analyze_meeting(transcript)
        apply_summary(meeting, analysis)
        db.commit()

        _set(db, job, status="extracting", stage="Extracting action items", progress=85)
        apply_actions(db, meeting, analysis)
        db.commit()

        _set(db, job, status="completed", stage="Ready", progress=100)
        logger.info("Processing job %s completed (meeting %s).", task_id, meeting.id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Processing job %s failed.", task_id)
        db.rollback()
        job = db.get(ProcessingJob, task_id)
        if job is not None:
            job.status = "failed"
            job.stage = "Failed"
            job.error = str(exc)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()

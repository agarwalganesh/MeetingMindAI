import os
import json
import shutil
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..database import get_db, SessionLocal
from ..models import Meeting, ActionItem, Decision, User, ChatMessage
from ..schemas import (
    MeetingResponse,
    MeetingDetailResponse,
    ActionItemResponse,
    DecisionResponse,
    ChatResponse,
    ChatMessageResponse,
    ProcessRequest,
    ProcessingJobResponse,
)
from ..utils import get_current_user, get_current_user_sse
from ..config import settings
from ..services.whisper_service import whisper_service
from ..services.ai_service import ai_service
from ..services.vector_service import vector_service
from ..services.pdf_service import pdf_service
from ..services import job_service

router = APIRouter(tags=["Meetings"])

# --- Helper schemas for requests ---
from pydantic import BaseModel

class TranscribeRequest(BaseModel):
    filename: str
    title: str

class SummarizeRequest(BaseModel):
    meeting_id: int

class ExtractActionsRequest(BaseModel):
    meeting_id: int

class GenerateReportRequest(BaseModel):
    meeting_id: int

class MeetingChatRequest(BaseModel):
    meeting_id: int
    message: str

# Number of prior conversation turns (user + assistant messages) sent to the
# LLM as context for multi-turn dialogue.
CHAT_HISTORY_LIMIT = 10

# --- Endpoints ---

@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    # Validate extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".mp3", ".wav", ".m4a", ".aac", ".ogg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload MP3, WAV, M4A, AAC, or OGG."
        )

    # Save file to uploads folder
    unique_filename = f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )

    return {
        "filename": unique_filename,
        "title": os.path.splitext(file.filename)[0]
    }


@router.post("/transcribe", response_model=MeetingDetailResponse)
def transcribe_meeting(
    req: TranscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    file_path = os.path.join(settings.UPLOAD_DIR, req.filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded file not found."
        )

    # Call transcription service
    try:
        transcript = whisper_service.transcribe_audio(file_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}"
        )

    # Create meeting record
    new_meeting = Meeting(
        user_id=current_user.id,
        title=req.title,
        filename=req.filename,
        transcript=transcript,
        sentiment_positive=0.0,
        sentiment_neutral=0.0,
        sentiment_negative=0.0
    )
    db.add(new_meeting)
    db.commit()
    db.refresh(new_meeting)

    # Index transcript in ChromaDB
    try:
        vector_service.index_meeting(new_meeting.id, transcript)
    except Exception as e:
        print(f"Indexing transcript failed: {e}")

    return new_meeting


# --- Asynchronous processing (task queue + real-time status) ---

@router.post("/process", response_model=ProcessingJobResponse, status_code=status.HTTP_202_ACCEPTED)
def process_meeting(
    req: ProcessRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Kick off transcription + summary + action extraction in the background.

    Returns immediately with a ``task_id``; the caller then polls
    ``GET /jobs/{task_id}`` or subscribes to ``GET /jobs/{task_id}/stream``
    rather than blocking the request (which risks gateway timeouts on large
    files).
    """
    file_path = os.path.join(settings.UPLOAD_DIR, req.filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded file not found."
        )

    job = job_service.create_and_start(db, current_user.id, req.filename, req.title)
    return job_service.serialize(job)


@router.get("/jobs/{task_id}", response_model=ProcessingJobResponse)
def get_job_status(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Poll a processing job's current status (polling fallback for SSE)."""
    job = job_service.get_job(db, task_id, current_user.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing job not found."
        )
    return job_service.serialize(job)


def _sse(payload: dict, event: Optional[str] = None) -> str:
    """Format a Server-Sent Events frame."""
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(payload, default=str)}\n\n"


@router.get("/jobs/{task_id}/stream")
async def stream_job_status(
    task_id: str,
    current_user: User = Depends(get_current_user_sse)
):
    """Stream a processing job's status over SSE until it reaches a terminal
    state. The DB row is the source of truth; each poll uses a fresh session so
    SQLite surfaces the background worker's latest committed writes."""
    POLL_INTERVAL = 1.0          # seconds between DB reads
    MAX_SECONDS = 60 * 30        # safety cap so a stuck job can't stream forever

    async def event_gen():
        last_snapshot = None
        elapsed = 0.0
        while elapsed <= MAX_SECONDS:
            db = SessionLocal()
            try:
                job = job_service.get_job(db, task_id, current_user.id)
                if job is None:
                    yield _sse({"error": "not_found", "task_id": task_id}, event="error")
                    return
                payload = job_service.serialize(job)
            finally:
                db.close()

            snapshot = (payload["status"], payload["progress"], payload["stage"])
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                yield _sse(payload)

            if payload["status"] in job_service.TERMINAL_STATUSES:
                return

            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # disable proxy buffering (e.g. nginx) so events flush live
    }
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)


@router.post("/summarize", response_model=MeetingDetailResponse)
def summarize_meeting(
    req: SummarizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == req.meeting_id,
        Meeting.user_id == current_user.id
    ).first()
    
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    if not meeting.transcript:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meeting has no transcript. Transcribe first."
        )

    # Run AI Analysis
    analysis = ai_service.analyze_meeting(meeting.transcript)
    job_service.apply_summary(meeting, analysis)

    db.commit()
    db.refresh(meeting)
    return meeting


@router.post("/extract-actions", response_model=MeetingDetailResponse)
def extract_actions(
    req: ExtractActionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == req.meeting_id,
        Meeting.user_id == current_user.id
    ).first()
    
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    if not meeting.transcript:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meeting has no transcript. Transcribe first."
        )

    # Analyze meeting (to extract actions & decisions)
    analysis = ai_service.analyze_meeting(meeting.transcript)
    job_service.apply_actions(db, meeting, analysis)

    db.commit()
    db.refresh(meeting)
    return meeting


@router.post("/generate-report")
def generate_report(
    req: GenerateReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == req.meeting_id,
        Meeting.user_id == current_user.id
    ).first()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    # Format data for PDF
    meeting_data = {
        "title": meeting.title,
        "created_at": meeting.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "filename": meeting.filename,
        "transcript": meeting.transcript,
        "summary_executive": meeting.summary_executive,
        "summary_detailed": meeting.summary_detailed,
        "summary_highlights": meeting.summary_highlights,
        "risks": meeting.risks,
        "follow_ups": meeting.follow_ups,
        "sentiment_positive": meeting.sentiment_positive,
        "sentiment_neutral": meeting.sentiment_neutral,
        "sentiment_negative": meeting.sentiment_negative,
        "action_items": [{"task": a.task, "owner": a.owner, "deadline": a.deadline, "priority": a.priority, "status": a.status} for a in meeting.action_items],
        "decisions": [d.decision_text for d in meeting.decisions]
    }

    report_filename = f"report_{meeting.id}_{int(datetime.utcnow().timestamp())}.pdf"
    
    try:
        pdf_path = pdf_service.generate_report(meeting_data, report_filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}"
        )

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{meeting.title.replace(' ', '_')}_Report.pdf"
    )


@router.post("/chat", response_model=ChatResponse)
def chat_meeting(
    req: MeetingChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == req.meeting_id,
        Meeting.user_id == current_user.id
    ).first()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    # Retrieve top chunks from Vector Store
    chunks = vector_service.query_meeting(meeting.id, req.message)
    context = "\n---\n".join(chunks) if chunks else meeting.transcript

    # Load the most recent prior turns (oldest first) for multi-turn context.
    recent = (
        db.query(ChatMessage)
        .filter(ChatMessage.meeting_id == meeting.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(CHAT_HISTORY_LIMIT)
        .all()
    )
    recent.reverse()
    history = [{"role": m.role, "content": m.content} for m in recent]

    # Synthesize response using the retrieved context and conversation history.
    response = ai_service.generate_chat_response(req.message, context, history)

    # Persist both sides of the exchange so future turns have full context.
    db.add(ChatMessage(meeting_id=meeting.id, role="user", content=req.message))
    db.add(ChatMessage(meeting_id=meeting.id, role="assistant", content=response))
    db.commit()

    return {
        "response": response,
        "sources": chunks
    }


@router.get("/meeting/{meeting_id}/chat-history", response_model=List[ChatMessageResponse])
def get_chat_history(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id
    ).first()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    return (
        db.query(ChatMessage)
        .filter(ChatMessage.meeting_id == meeting.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )


@router.delete("/meeting/{meeting_id}/chat-history")
def clear_chat_history(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id
    ).first()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    db.query(ChatMessage).filter(ChatMessage.meeting_id == meeting.id).delete()
    db.commit()

    return {"message": "Chat history cleared."}


@router.get("/meetings", response_model=List[MeetingResponse])
def get_meetings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Meeting).filter(Meeting.user_id == current_user.id).order_by(Meeting.created_at.desc()).all()


# Audio MIME types for streaming the original recording back to the player.
AUDIO_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
}


@router.get("/meeting/{meeting_id}/audio")
def get_meeting_audio(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Serve the original uploaded audio for a meeting so the frontend can
    render a waveform and play it back. Scoped to the meeting's owner."""
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id
    ).first()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    file_path = os.path.join(settings.UPLOAD_DIR, meeting.filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file for this meeting is no longer available."
        )

    ext = os.path.splitext(meeting.filename)[1].lower()
    media_type = AUDIO_MIME_TYPES.get(ext, "application/octet-stream")
    # FileResponse honours HTTP Range requests, enabling in-browser seeking.
    return FileResponse(file_path, media_type=media_type, filename=meeting.filename)


@router.get("/meeting/{id}", response_model=MeetingDetailResponse)
def get_meeting(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == id,
        Meeting.user_id == current_user.id
    ).first()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )
    return meeting


@router.delete("/meeting/{id}")
def delete_meeting(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == id,
        Meeting.user_id == current_user.id
    ).first()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    # Delete physical audio file
    file_path = os.path.join(settings.UPLOAD_DIR, meeting.filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error removing audio file: {e}")

    # Delete vector index
    try:
        vector_service.delete_meeting_index(meeting.id)
    except Exception as e:
        print(f"Error deleting vector index: {e}")

    # Delete DB records (cascading takes care of action items and decisions)
    db.delete(meeting)
    db.commit()

    return {"message": "Meeting successfully deleted."}


# Add inline update for action items directly from frontend
class ActionItemUpdatePayload(BaseModel):
    task: Optional[str] = None
    owner: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

@router.put("/action-item/{action_id}", response_model=ActionItemResponse)
def update_action_item(
    action_id: int,
    payload: ActionItemUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    action = db.query(ActionItem).join(Meeting).filter(
        ActionItem.id == action_id,
        Meeting.user_id == current_user.id
    ).first()

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action item not found or unauthorized."
        )

    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(action, field, val)

    db.commit()
    db.refresh(action)
    return action

# Add editable transcript update
class TranscriptUpdatePayload(BaseModel):
    transcript: str

@router.put("/meeting/{meeting_id}/transcript", response_model=MeetingDetailResponse)
def update_transcript(
    meeting_id: int,
    payload: TranscriptUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id
    ).first()

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found or unauthorized."
        )

    meeting.transcript = payload.transcript
    db.commit()
    db.refresh(meeting)

    # Reindex vector representation
    vector_service.index_meeting(meeting.id, payload.transcript)

    return meeting

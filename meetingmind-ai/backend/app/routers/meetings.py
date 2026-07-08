import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from ..models import Meeting, ActionItem, Decision, User
from ..schemas import MeetingResponse, MeetingDetailResponse, ActionItemResponse, DecisionResponse
from ..utils import get_current_user
from ..config import settings
from ..services.whisper_service import whisper_service
from ..services.ai_service import ai_service
from ..services.vector_service import vector_service
from ..services.pdf_service import pdf_service

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
    
    meeting.summary_executive = analysis.get("summary_executive")
    meeting.summary_detailed = analysis.get("summary_detailed")
    meeting.summary_highlights = analysis.get("summary_highlights")
    meeting.risks = "\n".join(analysis.get("risks", [])) if analysis.get("risks") else None
    meeting.follow_ups = "\n".join(analysis.get("follow_ups", [])) if analysis.get("follow_ups") else None
    
    sentiment = analysis.get("sentiment", {})
    meeting.sentiment_positive = sentiment.get("positive", 0.0)
    meeting.sentiment_neutral = sentiment.get("neutral", 0.0)
    meeting.sentiment_negative = sentiment.get("negative", 0.0)

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
    
    # Delete old action items/decisions
    db.query(ActionItem).filter(ActionItem.meeting_id == meeting.id).delete()
    db.query(Decision).filter(Decision.meeting_id == meeting.id).delete()

    # Save Action Items
    for item in analysis.get("action_items", []):
        new_action = ActionItem(
            meeting_id=meeting.id,
            task=item.get("task"),
            owner=item.get("owner", "Unassigned"),
            deadline=item.get("deadline"),
            priority=item.get("priority", "Medium"),
            status=item.get("status", "Pending")
        )
        db.add(new_action)

    # Save Decisions
    for dec_text in analysis.get("decisions", []):
        new_dec = Decision(
            meeting_id=meeting.id,
            decision_text=dec_text
        )
        db.add(new_dec)

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


@router.post("/chat")
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

    # Synthesize response
    response = ai_service.generate_chat_response(req.message, context)

    return {
        "response": response,
        "sources": chunks
    }


@router.get("/meetings", response_model=List[MeetingResponse])
def get_meetings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Meeting).filter(Meeting.user_id == current_user.id).order_by(Meeting.created_at.desc()).all()


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

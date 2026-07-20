from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from ..database import get_db
from ..models import User, Meeting, ActionItem, Decision
from ..schemas import UserResponse, MeetingResponse, UserAnalytics
from ..utils import get_current_admin
from ..services.vector_service import vector_service
import os
from ..config import settings

router = APIRouter(prefix="/admin", tags=["Admin Panel"])

@router.get("/analytics", response_model=UserAnalytics)
def get_global_analytics(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    total_users = db.query(User).count()
    total_meetings = db.query(Meeting).count()
    total_action_items = db.query(ActionItem).count()
    pending_tasks = db.query(ActionItem).filter(ActionItem.status == "Pending").count()
    completed_tasks = db.query(ActionItem).filter(ActionItem.status == "Completed").count()

    return {
        "total_users": total_users,
        "total_meetings": total_meetings,
        "total_action_items": total_action_items,
        "pending_tasks": pending_tasks,
        "completed_tasks": completed_tasks
    }

@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    total = db.query(User).count()
    users = db.query(User).offset(skip).limit(limit).all()
    results = []
    for u in users:
        meeting_count = db.query(Meeting).filter(Meeting.user_id == u.id).count()
        results.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "created_at": u.created_at,
            "meeting_count": meeting_count
        })
    return {"total": total, "skip": skip, "limit": limit, "items": results}

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own admin account."
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Delete all associated meetings physically and in vector store
    user_meetings = db.query(Meeting).filter(Meeting.user_id == target_user.id).all()
    for meeting in user_meetings:
        # Physical audio file delete
        file_path = os.path.join(settings.UPLOAD_DIR, meeting.filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        # Vector delete
        try:
            vector_service.delete_meeting_index(meeting.id)
        except Exception:
            pass

    db.delete(target_user)
    db.commit()
    return {"message": f"User {target_user.email} and all associated data deleted successfully."}

@router.get("/meetings")
def list_all_meetings(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    total = db.query(Meeting).count()
    meetings = db.query(Meeting).offset(skip).limit(limit).all()
    results = []
    for m in meetings:
        owner = db.query(User).filter(User.id == m.user_id).first()
        results.append({
            "id": m.id,
            "title": m.title,
            "filename": m.filename,
            "created_at": m.created_at,
            "user_email": owner.email if owner else "Unknown",
            "user_name": owner.name if owner else "Unknown"
        })
    return {"total": total, "skip": skip, "limit": limit, "items": results}

@router.delete("/meetings/{meeting_id}")
def delete_any_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found."
        )

    # Physical delete
    file_path = os.path.join(settings.UPLOAD_DIR, meeting.filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
            
    # Vector delete
    try:
        vector_service.delete_meeting_index(meeting.id)
    except Exception:
        pass

    db.delete(meeting)
    db.commit()
    return {"message": "Meeting deleted successfully."}

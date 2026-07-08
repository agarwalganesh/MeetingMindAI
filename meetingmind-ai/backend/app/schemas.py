from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

# --- User Schemas ---
class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[str] = None

# --- Action Item Schemas ---
class ActionItemBase(BaseModel):
    task: str
    owner: Optional[str] = "Unassigned"
    deadline: Optional[str] = None
    priority: Optional[str] = "Medium"
    status: Optional[str] = "Pending"

class ActionItemCreate(ActionItemBase):
    pass

class ActionItemUpdate(BaseModel):
    task: Optional[str] = None
    owner: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

class ActionItemResponse(ActionItemBase):
    id: int
    meeting_id: int

    class Config:
        from_attributes = True

# --- Decision Schemas ---
class DecisionBase(BaseModel):
    decision_text: str

class DecisionCreate(DecisionBase):
    pass

class DecisionResponse(DecisionBase):
    id: int
    meeting_id: int

    class Config:
        from_attributes = True

# --- Meeting Schemas ---
class MeetingBase(BaseModel):
    title: str

class MeetingCreate(MeetingBase):
    filename: str

class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    transcript: Optional[str] = None

class MeetingResponse(MeetingBase):
    id: int
    user_id: int
    filename: str
    created_at: datetime
    sentiment_positive: float
    sentiment_neutral: float
    sentiment_negative: float

    class Config:
        from_attributes = True

class MeetingDetailResponse(MeetingResponse):
    transcript: Optional[str] = None
    summary_executive: Optional[str] = None
    summary_detailed: Optional[str] = None
    summary_highlights: Optional[str] = None
    risks: Optional[str] = None
    follow_ups: Optional[str] = None
    action_items: List[ActionItemResponse] = []
    decisions: List[DecisionResponse] = []

    class Config:
        from_attributes = True

# --- RAG Chat Schemas ---
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    sources: List[str] = []

# --- Admin Panel / Analytics Schemas ---
class UserAnalytics(BaseModel):
    total_users: int
    total_meetings: int
    total_action_items: int
    pending_tasks: int
    completed_tasks: int

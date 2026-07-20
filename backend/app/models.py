# pyrefly: ignore [missing-import]
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")  # 'user' or 'admin'
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    meetings = relationship("Meeting", back_populates="user", cascade="all, delete-orphan")

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    transcript = Column(Text, nullable=True)
    summary_executive = Column(Text, nullable=True)
    summary_detailed = Column(Text, nullable=True)
    summary_highlights = Column(Text, nullable=True)
    risks = Column(Text, nullable=True)
    follow_ups = Column(Text, nullable=True)
    
    # Sentiment scores
    sentiment_positive = Column(Float, default=0.0)
    sentiment_neutral = Column(Float, default=0.0)
    sentiment_negative = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="meetings")
    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="meeting", cascade="all, delete-orphan")
    chat_messages = relationship(
        "ChatMessage",
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    task = Column(String, nullable=False)
    owner = Column(String, default="Unassigned")
    deadline = Column(String, nullable=True)
    priority = Column(String, default="Medium")  # Low, Medium, High
    status = Column(String, default="Pending")  # Pending, Completed

    # Relationships
    meeting = relationship("Meeting", back_populates="action_items")

class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    decision_text = Column(Text, nullable=False)

    # Relationships
    meeting = relationship("Meeting", back_populates="decisions")

class ProcessingJob(Base):
    """An asynchronous transcription + analysis job.

    Created by ``POST /process`` and worked in a background thread so the HTTP
    request returns immediately with a ``task_id`` instead of blocking on
    Whisper/LLM calls. The row is the durable source of truth for both polling
    (``GET /jobs/{id}``) and the live SSE stream (``GET /jobs/{id}/stream``).
    """
    __tablename__ = "processing_jobs"

    # Opaque, unguessable id used as the public task_id.
    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Set once transcription produces a meeting record; null while queued/running.
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)

    filename = Column(String, nullable=False)
    title = Column(String, nullable=False)

    # Lifecycle: queued -> transcribing -> summarizing -> extracting -> completed
    #            (or -> failed at any point).
    status = Column(String, nullable=False, default="queued")
    stage = Column(String, nullable=True)      # human-readable label for the UI
    progress = Column(Integer, default=0)      # 0-100
    error = Column(Text, nullable=True)        # populated when status == "failed"

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatMessage(Base):
    """A single turn in the conversational RAG chat for a meeting.

    Persisting messages lets the /chat endpoint pass previous turns back to the
    LLM so it can answer follow-up questions with the context of the dialogue.
    """
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    meeting = relationship("Meeting", back_populates="chat_messages")

from sqlalchemy import Column, String, DateTime, Float
from datetime import datetime
import uuid
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    google_id = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, index=True)
    user_email = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False) # 'user' or 'assistant'
    content = Column(String, nullable=False)
    structured_content = Column(String, nullable=True) # JSON string
    sources = Column(String, nullable=True) # JSON string
    model_used = Column(String, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

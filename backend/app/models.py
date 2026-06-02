from datetime import datetime
import uuid

from sqlalchemy import Column,String,Text,DateTime,ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True,nullable=False)
    fullname = Column(String, nullable=True)
    email = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False,onupdate=datetime.utcnow)
    rooms = relationship("Room", back_populates="users")
    password = Column(String, nullable=False)

class Room(Base):
    __tablename__ = "rooms"
    title = Column(String,nullable=False)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False,onupdate=datetime.utcnow)
    users = relationship("User", back_populates="rooms")
    docs = relationship("DOC", back_populates="rooms")

class DOC(Base):
    __tablename__ = "docs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False)
    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    public_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False,onupdate=datetime.utcnow)
    rooms = relationship("Room", back_populates="docs")
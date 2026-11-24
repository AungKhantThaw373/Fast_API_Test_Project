from datetime import datetime
import uuid

from sqlalchemy import Column,String,Text,DateTime,ForeignKey,Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db import Base

EMBED_DIM = 384

class Course(Base):
    __tablename__ = "courses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class CourseDoc(Base):
    __tablename__ = "course_docs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(1024), nullable=False)
    content_type = Column(String(64), nullable=False)     # pdf/pptx/xlsx/image
    storage_path = Column(Text, nullable=False)           # Supabase storage path or URL
    status = Column(String(32), nullable=False, default="uploaded")  # uploaded|processing|processed|failed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class CourseChunk(Base):
    __tablename__ = "course_chunks"
    __table_args__ = (
        UniqueConstraint("course_doc_id", "chunk_index", name="uq_course_chunks_doc_chunk_index"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    course_doc_id = Column(UUID(as_uuid=True), ForeignKey("course_docs.id", ondelete="CASCADE"), nullable=False, index=True)

    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    chunk_metadata = Column("metadata", JSONB, nullable=False, default=dict)

    embedding = Column(Vector(EMBED_DIM), nullable=False)

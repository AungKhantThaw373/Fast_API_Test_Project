import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base


class EditingFolder(Base):
    __tablename__ = "editing_folders"
    __table_args__ = (
        UniqueConstraint("owner_id", "canonical_name", name="uq_editing_folder_owner_name"),
        Index("ix_editing_folders_owner", "owner_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    canonical_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    files = relationship("DraftFile", back_populates="folder", cascade="all, delete-orphan")


class DraftFile(Base):
    __tablename__ = "editing_draft_files"
    __table_args__ = (
        Index("ix_editing_draft_files_folder", "folder_id", "updated_at"),
        Index("ix_editing_draft_files_owner", "owner_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("editing_folders.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    original_filename = Column(String(255), nullable=False)
    extension = Column(String(20), nullable=False)
    media_type = Column(String(120), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    content = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    folder = relationship("EditingFolder", back_populates="files")

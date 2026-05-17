from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.supabase_storage import supabase
from fastapi import Form,UploadFile, File
import uuid
from app.models import DOC
from app.db import get_async_session

router = APIRouter()

@router.get("/docs")
async def read_docs(session: AsyncSession = Depends(get_async_session)):
    # This is a placeholder endpoint for documentation purposes.
    # You can implement actual logic here if needed.
    return {"message": "This is the documentation endpoint."}

@router.post("/upload")
async def upload_to_supabase(session: AsyncSession = Depends(get_async_session), file: UploadFile = File(...),room_id:uuid.UUID = Form(...)):
    # 1. generate safe filename
    file_id = str(uuid.uuid4())
    file_path = f"{file_id}.{file.filename.split('.')[-1]}"

    # 2. read file
    contents = await file.read()

    # 3. upload to Supabase Storage
    supabase.storage.from_("documents").upload(
        path=file_path,
        file=contents,
        file_options={"content-type": file.content_type}
    )

    # 4. get public URL
    res = supabase.storage.from_("documents").get_public_url(file_path)
    public_url = res

    doc = DOC(
        room_id=room_id,
        filename=file.filename,
        storage_path=file_path,
        public_url=public_url
    )

    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    return doc

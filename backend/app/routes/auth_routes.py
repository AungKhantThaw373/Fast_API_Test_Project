from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_async_session
from backend.app.models import Room
from backend.app.schemas.rooms import RoomCreate

router = APIRouter()
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_async_session
from backend.app.models import Room
from backend.app.schemas.rooms import RoomCreate

router = APIRouter()

# Endpoint to read all rooms
@router.get("/rooms")
async def read_rooms(session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Room).order_by(Room.created_at.desc()))
    rooms = [row[0] for row in result.all()]
    rooms_data = [
        {
            "id": str(room.id),
            "title": room.title,
            "user_id": room.user_id,
            "created_at": room.created_at.isoformat(),
            "updated_at": room.updated_at.isoformat()
        }
        for room in rooms
    ]
    return {"rooms": rooms_data}

# Endpoint to create a new room
@router.post("/rooms")
async def create_room(
    room_create: RoomCreate,
    session: AsyncSession = Depends(get_async_session)
):
    room = Room(title=room_create.title, user_id="test_user")
    session.add(room)
    await session.commit()
    await session.refresh(room)
    return room

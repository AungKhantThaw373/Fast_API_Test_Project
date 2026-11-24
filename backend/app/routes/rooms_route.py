from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_async_session
from app.models.app_models import Room
from app.schemas.rooms import RoomCreate
from app.security import get_current_user
from app.schemas.user import CurrentUser
from app.models.app_models import User

router = APIRouter()

# Endpoint to read all rooms
@router.get("/rooms")
async def read_rooms(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
):
    query = select(Room).join(User, Room.user_id == User.id).where(User.username == current_user.username).order_by(Room.created_at.desc())
    result = await session.execute(query)
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
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(User).where(User.username == current_user.username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    room = Room(title=room_create.title, user_id=user.id)
    session.add(room)
    await session.commit()
    await session.refresh(room)
    return room

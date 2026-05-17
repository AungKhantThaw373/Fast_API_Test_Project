from fastapi import APIRouter, Depends,HTTPException,status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_async_session
from app.models import User
from app.schemas.auth import UserCreate

router = APIRouter()

@router.get("/users")
async def get_users(session: AsyncSession = Depends(get_async_session)):
    query = select(User)
    result = await session.execute(query)
    users = [row[0] for row in result.all()]
    users_data = [
        {
            "id": str(user.id),
            "email": user.email,
            "created_at": user.created_at.isoformat()
        }
        for user in users
    ]
    return {"users": users_data}        

@router.post("/signup",status_code=201)
async def signup(user_in: UserCreate, session: AsyncSession = Depends(get_async_session)):
    query = select(User).where(User.email == user_in.email)
    result =await session.execute(query)
    user=result.scalar_one_or_none()
    if user:
        raise HTTPException(status_code=400,detail="Email already registered")
    user = User(email=user_in.email,password=user_in.password)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {"id": str(user.id), "email": user.email}
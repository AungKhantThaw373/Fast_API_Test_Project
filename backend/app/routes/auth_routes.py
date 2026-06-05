from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends,HTTPException,Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.security import OAuth2PasswordRequestForm

from app.security import verify_password, create_access_token
from app.config import settings
from app.db import get_async_session
from app.models import User
from app.schemas.auth import Token, UserCreate
from app.security import get_password_hash

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

@router.post("/register",status_code=201)
async def signup(user_in: UserCreate, session: AsyncSession = Depends(get_async_session)):
    query = select(User).where(User.email == user_in.email)
    result =await session.execute(query)
    user=result.scalar_one_or_none()
    if user:
        raise HTTPException(status_code=400,detail="Email already registered")
    user = User(username=user_in.username,email=user_in.email,password=get_password_hash(user_in.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {"id": str(user.id), "email": user.email}

@router.post("/token",response_model=Token)
async def login(response: Response, form_data: Annotated[OAuth2PasswordRequestForm, Depends()], session: AsyncSession = Depends(get_async_session)):
    query = select(User).where(User.email == form_data.username)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=400,detail="Incorrect email or password")
    
    if not verify_password(form_data.password,user.password):
        raise HTTPException(status_code=400,detail="Incorrect email or password")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    response.set_cookie(
        key="token",
        value=access_token,
        httponly=True,  
        samesite="lax",
        secure=False,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )
    return Token(access_token=access_token, token_type="bearer")

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="token", path="/")
    return {"message": "Logged out successfully"}


from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_async_session
from app.models.app_models import User
from app.schemas.auth import UserCreate, normalize_email
from app.security import create_access_token, get_password_hash, verify_password

router = APIRouter(tags=["authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    session: AsyncSession = Depends(get_async_session),
):
    exists = await session.scalar(
        select(User.id).where(
            (func.lower(User.email) == user_in.email.strip().lower())
            | (User.username == user_in.username)
        )
    )
    if exists:
        raise HTTPException(status_code=409, detail="That email or username is already in use.")

    user = User(
        username=user_in.username,
        email=user_in.email,
        password=get_password_hash(user_in.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="That email or username is already in use.") from None
    await session.refresh(user)
    return {"id": str(user.id), "username": user.username, "email": user.email}


@router.post("/token")
async def login(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncSession = Depends(get_async_session),
):
    email = normalize_email(form_data.username)
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    access_token = create_access_token(user.id)
    response.set_cookie(
        key="token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return {"message": "Signed in."}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="token", path="/")
    return {"message": "Signed out."}

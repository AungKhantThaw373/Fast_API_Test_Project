from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt

from pwdlib import PasswordHash
from jwt.exceptions import InvalidTokenError
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends,Cookie
from fastapi import HTTPException, status

from app.db import get_async_session
from app.config import settings
from app.schemas.user import CurrentUser

password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

def verify_password(plain_password: str, hashed_password:str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    return encoded_jwt

async def get_current_user(token: Annotated[str | None, Cookie()] = None ) -> CurrentUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")

        if not username:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    
    current_user = CurrentUser(  
        username=username,
    )

    return current_user
    
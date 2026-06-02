from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.security import get_current_user
from app.schemas.user import CurrentUser
from app.models import User

router = APIRouter()

@router.post("/update")
async def update_username(user_in:str,current_user:Annotated[CurrentUser,Depends(get_current_user)],session:AsyncSession=Depends(get_async_session)):
    user=await session.execute(select(User).where(User.username==current_user.username))
    

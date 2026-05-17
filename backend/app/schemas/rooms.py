from pydantic import BaseModel

class RoomCreate(BaseModel):
    title: str
    user_id: str
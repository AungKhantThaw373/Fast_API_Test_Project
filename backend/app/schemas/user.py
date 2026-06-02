from pydantic import BaseModel, EmailStr

class CurrentUser(BaseModel):
    id: int | None = None
    username: str
    email: EmailStr | None = None

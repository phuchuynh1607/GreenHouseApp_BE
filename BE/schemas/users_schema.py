from typing import Optional

from pydantic import BaseModel, Field


class UserVerification(BaseModel):
    password:str
    new_password:str=Field(min_length=6)

class UserUpdateRequest(BaseModel):
    first_name:str=Field(min_length=1)
    last_name:str=Field(min_length=1)
    phone_number:str=Field(min_length=5)
    gender: Optional[str] = None
    user_image: Optional[str] = None

class CreateUserRequest(BaseModel):
    username:str
    email:str
    first_name:str
    last_name:str
    password:str
    role:str
    phone_number:str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    role: str
    phone_number: str
    gender: Optional[str] = None
    user_image: Optional[str] = None

    class Config:
        from_attributes = True


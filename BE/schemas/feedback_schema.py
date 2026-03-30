from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class MessageCreate(BaseModel):
    message_content: str

class MessageResponse(BaseModel):
    id: int
    sender_id: int
    message_content: str
    created_at: datetime

    class Config:
        from_attributes = True

class TicketCreate(BaseModel):
    subject: str
    initial_message: str

class TicketResponse(BaseModel):
    id: int
    user_id: int
    subject: str
    status: str
    created_at: datetime
    # SQLAlchemy tự động đổ dữ liệu vào đây nhờ relationship
    messages: List[MessageResponse]

    class Config:
        from_attributes = True
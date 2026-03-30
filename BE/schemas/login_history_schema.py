from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class LoginHistoryResponse(BaseModel):
    id: int
    login_time: datetime
    ip_address: Optional[str]
    device_info: Optional[str]

    class Config:
        from_attributes = True
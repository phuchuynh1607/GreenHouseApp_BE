from pydantic import BaseModel
from typing import Optional

class ThresholdCreate(BaseModel):
    sensor_type: str # 'temp', 'light', 'soil'
    min_value: float
    max_value: float

class ThresholdResponse(BaseModel):
    id: int
    sensor_type: str
    min_value: float
    max_value: float
    user_id: Optional[int]

    class Config:
        from_attributes = True
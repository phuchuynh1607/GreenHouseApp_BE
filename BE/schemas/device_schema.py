from pydantic import BaseModel, Field, field_validator, ValidationInfo
from datetime import datetime
from typing import Optional



class SensorLogCreate(BaseModel):
    temp: float
    humi: float
    light: float
    soil: float

class SensorLogResponse(SensorLogCreate):
    id: int
    timestamp: datetime
    class Config:
        from_attributes = True


class DeviceControlRequest(BaseModel):
    device_index: int = Field(..., description="0: Light, 1: Fan, 2: Pump")
    mode: Optional[int] = Field(None, ge=0, le=2, description="0: Off, 1: Auto, 2: Manual")
    manual_pwm: Optional[int] = Field(None, ge=0, le=255)
    start_hour: Optional[int] = Field(None, ge=-1, le=23)
    end_hour: Optional[int] = Field(None, ge=-1, le=23)

    @field_validator('start_hour', 'end_hour')
    @classmethod
    def validate_hour(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < -1 or v > 23):
            raise ValueError('Hour must be -1 or between 0-23')
        return v


class DeviceResponse(BaseModel):
    id: int
    device_index: int
    name: str
    mode: int
    manual_pwm: int
    start_hour: int
    end_hour: int

    class Config:
        from_attributes = True
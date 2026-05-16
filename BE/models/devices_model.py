from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.sql import func
from ..database import Base

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_index = Column(Integer, unique=True, nullable=False)
    name = Column(String(100))
    # 0: OFF, 1: AUTO (dựa trên Threshold), 2: MANUAL (bật theo PWM)
    mode = Column(Integer, default=0)
    # Giá trị PWM (0-255). Nếu mode=1, giá trị này dùng để chạy khi cảm biến đạt ngưỡng
    manual_pwm = Column(Integer, default=128)
    # Giá trị -1 nghĩa là chạy 24/24 (không hẹn giờ)
    start_hour = Column(Integer, default=-1)
    end_hour = Column(Integer, default=-1)


class SensorLogs(Base):
    __tablename__ = "sensor_logs"

    id = Column(Integer, primary_key=True, index=True)
    temp = Column(Float)
    humi = Column(Float)
    light = Column(Float)
    soil = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
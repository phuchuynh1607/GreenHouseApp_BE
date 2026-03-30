from sqlalchemy import Column, Integer, ForeignKey, String, Float, DateTime,Boolean
from sqlalchemy.sql import func
from BE.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    sensor_type = Column(String(50))  # temp, soil, light...
    message = Column(String(255))

    current_value = Column(Float)
    threshold_value = Column(Float)

    # Chỉ cần thời gian để hiển thị trên FlatList
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_read = Column(Boolean, default=False)
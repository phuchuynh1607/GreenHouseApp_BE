from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from BE.database import Base


class Users(Base):
    __tablename__='users'

    id=Column(Integer,primary_key=True,index=True)
    email=Column(String,unique=True)
    username=Column(String,unique=True,nullable=False)
    first_name=Column(String)
    last_name=Column(String)
    hashed_password=Column(String)
    role=Column(String, default="user")
    phone_number=Column(String)
    is_active = Column(Boolean, default=True)
    gender = Column(String,nullable=True)
    user_image=Column(String,nullable=True)

    thresholds = relationship("Threshold", back_populates="owner", cascade="all, delete-orphan")
    # Quan hệ mới: Một người dùng có nhiều bản ghi lịch sử đăng nhập
    login_histories = relationship("LoginHistory", back_populates="user", cascade="all, delete-orphan")
    tickets = relationship("FeedbackTicket", back_populates="user", cascade="all, delete-orphan")

class Threshold(Base):
    __tablename__='thresholds'

    id = Column(Integer, primary_key=True, index=True)
    sensor_type=Column(String, nullable=False) #temp,humi,light,soil
    min_value=Column(Float)
    max_value=Column(Float)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner = relationship("Users", back_populates="thresholds")



class LoginHistory(Base):
    __tablename__ = "login_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    # Thời gian đăng nhập (Tự động lấy giờ hệ thống server)
    login_time = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)  # <--- Thêm dòng này

    # Có thể lưu thêm thông tin bổ sung nếu muốn (Ví dụ: IP hoặc Thiết bị)
    device_info = Column(String, nullable=True)

    # --- RELATIONSHIP ---
    user = relationship("Users", back_populates="login_histories")

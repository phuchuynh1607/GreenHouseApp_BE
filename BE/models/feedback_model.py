from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

class FeedbackTicket(Base):
    __tablename__ = "feedback_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    subject = Column(String(255))
    status = Column(String, default="pending") # pending, processing, resolved, closed
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Quan hệ
    user = relationship("Users", back_populates="tickets")
    messages = relationship("FeedbackMessage", back_populates="ticket", cascade="all, delete-orphan")

class FeedbackMessage(Base):
    __tablename__ = "feedback_messages"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("feedback_tickets.id"))
    sender_id = Column(Integer, ForeignKey("users.id"))
    message_content = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Quan hệ
    ticket = relationship("FeedbackTicket", back_populates="messages")
    sender = relationship("Users")
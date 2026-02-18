import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    HOSPITAL_ADMIN = "hospital_admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    LAB_ASSISTANT = "lab_assistant"
    PATIENT = "patient"
    BASE = "base"

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    phone_number = Column(String, nullable=True)
    role = Column(String, default=UserRole.BASE.value)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    compact_id = Column(String, unique=True, index=True, nullable=True)
    image = Column(String, nullable=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    hospital = relationship("Hospital", back_populates="users")
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False, primaryjoin="User.id == Doctor.user_id")
    nurse_profile = relationship("Nurse", back_populates="user", uselist=False, primaryjoin="User.id == Nurse.user_id")
    documents = relationship("Document", back_populates="owner")

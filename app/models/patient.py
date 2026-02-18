import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base

class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Link to auto-created user account
    full_name = Column(String, index=True)
    age = Column(Integer)
    gender = Column(String)
    phone = Column(String, nullable=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False)
    assigned_doctor_id = Column(String, ForeignKey("doctors.id"), nullable=True)
    assigned_nurse_id = Column(String, ForeignKey("nurses.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User")
    hospital = relationship("Hospital", back_populates="patients")
    assigned_doctor = relationship("Doctor", back_populates="patients")
    assigned_nurse = relationship("Nurse") # Backref could be added if needed
    appointments = relationship("Appointment", back_populates="patient")

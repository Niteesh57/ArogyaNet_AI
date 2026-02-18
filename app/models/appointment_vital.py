import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base

class AppointmentVital(Base):
    __tablename__ = "appointment_vitals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    appointment_id = Column(String, ForeignKey("appointments.id"), nullable=False)
    bp = Column(String, nullable=False) # Blood Pressure (e.g. "120/80")
    pulse = Column(Integer, nullable=False)
    temp = Column(Float, nullable=False)
    resp = Column(Integer, nullable=False)
    spo2 = Column(Integer, nullable=False)
    remarks = Column(String, nullable=True)
    nurse_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    appointment = relationship("Appointment", back_populates="vital_logs")
    nurse = relationship("User")

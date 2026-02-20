import uuid
from datetime import datetime, timezone, date
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum

class SeverityLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AppointmentStatus(str, enum.Enum):
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    ADMITTED = "admitted"

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=False)
    description = Column(String)
    date = Column(Date, nullable=False)
    slot = Column(String, nullable=False)  # e.g., "10:30", "11:00", "11:30"
    status = Column(String, default=AppointmentStatus.STARTED.value)
    severity = Column(String, default=SeverityLevel.LOW.value)
    remarks = Column(JSON, nullable=True)  # {text: str, lab: [], medicine: []}
    # vitals = Column(JSON, default=list) # Deprecated, use AppointmentVital table
    next_followup = Column(Date, nullable=True)
    nurse_id = Column(String, ForeignKey("users.id"), nullable=True) # Link to User (Nurse role)
    lab_report_id = Column(String, ForeignKey("lab_reports.id"), nullable=True)
    diet_plan = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("Doctor")
    nurse = relationship("User", foreign_keys=[nurse_id])
    lab_report = relationship("LabReport", back_populates="appointments")
    vital_logs = relationship("AppointmentVital", back_populates="appointment")

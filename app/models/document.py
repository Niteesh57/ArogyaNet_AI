from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base
import uuid

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    file_url = Column(String, nullable=False)
    file_type = Column(String, nullable=True) # e.g. 'application/pdf', 'image/jpeg'
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    appointment_id = Column(String, ForeignKey("appointments.id"), nullable=True)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=True)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="documents")

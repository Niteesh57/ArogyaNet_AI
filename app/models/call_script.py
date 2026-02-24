import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from app.core.database import Base

class CallScript(Base):
    __tablename__ = "call_scripts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    appointment_id = Column(String, ForeignKey("appointments.id"), nullable=False)
    speaker = Column(String, nullable=False)  # 'agent' or 'user'
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

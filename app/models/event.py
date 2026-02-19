import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base

class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_name = Column(String, nullable=True)
    
    # Stores a list of JSON objects: [{"key": "value", "timestamp": "...", "nurse": "..."}]
    json_data = Column(JSON, default=list) 

    # Stores a list of strings defining the expected keys for this event type
    keys = Column(JSON, default=list)
    
    created_by_id = Column(String, ForeignKey("users.id"))
    updated_by_id = Column(String, ForeignKey("users.id"))
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])

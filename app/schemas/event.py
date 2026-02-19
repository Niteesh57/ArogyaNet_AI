from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime

# Shared properties
class EventBase(BaseModel):
    event_name: Optional[str] = None

# Properties to receive on item creation
class EventCreate(EventBase):
    keys: List[str] = [] # List of key names expected for this event

# Properties to receive on item update
class EventUpdate(EventBase):
    json_data: Optional[List[Dict[str, Any]]] = None
    keys: Optional[List[str]] = None

# Properties to append data
class EventDataAppend(BaseModel):
    data: Dict[str, Any]

# Properties to return to client
class Event(EventBase):
    id: str
    keys: Optional[List[str]] = None
    json_data: List[Dict[str, Any]] = []
    created_by_id: str
    updated_by_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

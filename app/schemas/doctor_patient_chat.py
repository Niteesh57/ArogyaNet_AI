from pydantic import BaseModel
from datetime import datetime

class ChatMessageBase(BaseModel):
    message: str

class ChatMessageCreate(ChatMessageBase):
    receiver_id: str

class ChatMessageResponse(ChatMessageBase):
    id: int
    sender_id: str
    receiver_id: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChatContact(BaseModel):
    id: str
    full_name: str
    role: str
    image: str | None = None
    hospital_name: str | None = None
    specialization: str | None = None
    last_message: ChatMessageResponse | None = None

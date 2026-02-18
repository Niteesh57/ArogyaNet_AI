from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.schemas.user import User

class AppointmentVitalBase(BaseModel):
    bp: str
    pulse: int
    temp: float
    resp: int
    spo2: int
    remarks: Optional[str] = None

class AppointmentVitalInput(AppointmentVitalBase):
    pass

class AppointmentVitalCreate(AppointmentVitalBase):
    appointment_id: str
    nurse_id: str

class AppointmentVitalUpdate(AppointmentVitalBase):
    pass

class AppointmentVitalInDBBase(AppointmentVitalBase):
    id: str
    appointment_id: str
    nurse_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AppointmentVitalResponse(AppointmentVitalInDBBase):
    nurse: Optional[User] = None

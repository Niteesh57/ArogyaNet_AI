from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel, EmailStr
from app.models.appointment import SeverityLevel

# Remarks structure for appointments
class AppointmentRemarks(BaseModel):
    text: Optional[str] = None
    lab: list = []
    medicine: list = []

class AppointmentBase(BaseModel):
    patient_id: str
    doctor_id: str
    description: Optional[str] = None  # Optional
    date: date  # Mandatory
    slot: str  # Mandatory - e.g., "10:30", "11:00", "11:30"
    severity: SeverityLevel  # Mandatory
    remarks: Optional[AppointmentRemarks] = None  # Optional
    next_followup: Optional[date] = None  # Optional
    lab_report_id: Optional[str] = None

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentCreateWithoutPatient(BaseModel):
    doctor_id: str
    description: Optional[str] = None
    date: date
    slot: str
    severity: SeverityLevel
    remarks: Optional[AppointmentRemarks] = None
    next_followup: Optional[date] = None
    lab_report_id: Optional[str] = None

class AppointmentUpdate(BaseModel):
    doctor_id: Optional[str] = None
    description: Optional[str] = None
    date: Optional[date] = None
    slot: Optional[str] = None
    severity: Optional[SeverityLevel] = None
    remarks: Optional[AppointmentRemarks] = None
    next_followup: Optional[date] = None
    lab_report_id: Optional[str] = None

class Appointment(AppointmentBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

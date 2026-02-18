from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, EmailStr
from app.models.appointment import SeverityLevel, AppointmentStatus

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
    status: AppointmentStatus = AppointmentStatus.STARTED
    severity: SeverityLevel  # Mandatory
    remarks: Optional[AppointmentRemarks] = None  # Optional
    next_followup: Optional[date] = None  # Optional
    nurse_id: Optional[str] = None
    lab_report_id: Optional[str] = None

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentCreateWithoutPatient(BaseModel):
    doctor_id: str
    description: Optional[str] = None
    date: date
    slot: str
    status: AppointmentStatus = AppointmentStatus.STARTED
    severity: SeverityLevel
    remarks: Optional[AppointmentRemarks] = None
    next_followup: Optional[date] = None
    nurse_id: Optional[str] = None
    lab_report_id: Optional[str] = None

class AppointmentUpdate(BaseModel):
    doctor_id: Optional[str] = None
    description: Optional[str] = None
    date: Optional[date] = None
    slot: Optional[str] = None
    status: Optional[AppointmentStatus] = None
    severity: Optional[SeverityLevel] = None
    remarks: Optional[AppointmentRemarks] = None
    next_followup: Optional[date] = None
    nurse_id: Optional[str] = None
    lab_report_id: Optional[str] = None

class Appointment(AppointmentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    nurse_name: Optional[str] = None  # Added field for convenience
    vitals: Optional[List["AppointmentVitalResponse"]] = None # List of AppointmentVitalResponse

    class Config:
        from_attributes = True

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from app.schemas.doctor import DoctorResponse
    from app.schemas.hospital import Hospital
    from app.schemas.patient import Patient
    from app.schemas.appointment_vital import AppointmentVitalResponse

class AppointmentWithDoctor(Appointment):
    doctor_name: Optional[str] = None
    doctor_specialization: Optional[str] = None
    hospital_name: Optional[str] = None
    doctor: Optional["DoctorResponse"] = None
    hospital: Optional["Hospital"] = None
    patient: Optional["Patient"] = None

from app.schemas.doctor import DoctorResponse
from app.schemas.hospital import Hospital
from app.schemas.patient import Patient
from app.schemas.appointment_vital import AppointmentVitalResponse

Appointment.model_rebuild()
AppointmentWithDoctor.model_rebuild()

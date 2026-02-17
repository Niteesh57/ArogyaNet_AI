"""
Summarize Model for AI Agent
Output schema for appointment creation from conversation summary
"""
from typing import Optional
from datetime import date
from pydantic import BaseModel, Field
from app.models.appointment import SeverityLevel


class AppointmentSummary(BaseModel):
    """
    Model for summarizing appointment details from conversation.
    Used by AI agent to extract structured appointment data.
    """
    doctor_id: str = Field(
        ..., 
        description="The ID of the doctor for the appointment"
    )
    
    slot_time: str = Field(
        ..., 
        description="Time slot for appointment in HH:MM format (e.g., '10:30', '14:00')",
        pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"
    )
    
    severity: SeverityLevel = Field(
        ..., 
        description="Severity level of the appointment: low, medium, high, or critical"
    )
    
    enhanced_description: str = Field(
        ..., 
        description="Enhanced description of the patient's condition and reason for appointment",
        min_length=10
    )
    
    # Optional fields
    appointment_date: Optional[date] = Field(
        None,
        description="Date of the appointment (defaults to today if not specified)"
    )
    
    patient_id: Optional[str] = Field(
        None,
        description="Patient ID if known"
    )
    
    next_followup: Optional[date] = Field(
        None,
        description="Next follow-up date if mentioned"
    )
    
    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "doctor_id": "doctor-uuid-123",
                "slot_time": "10:30",
                "severity": "medium",
                "enhanced_description": "Patient experiencing persistent headaches for 3 days with mild nausea. No fever. Requesting consultation for neurological evaluation.",
                "appointment_date": "2026-02-20",
                "patient_id": "patient-uuid-456",
                "next_followup": "2026-03-20"
            }
        }


class ConversationSummary(BaseModel):
    """
    Model for summarizing entire conversation about appointment booking.
    """
    summary_text: str = Field(
        ...,
        description="Natural language summary of the conversation"
    )
    
    appointment_details: AppointmentSummary = Field(
        ...,
        description="Structured appointment data extracted from conversation"
    )
    
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of the extraction (0.0 to 1.0)"
    )
    
    missing_information: list[str] = Field(
        default_factory=list,
        description="List of information that is still needed"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "summary_text": "Patient John Doe wants to book appointment with Dr. Smith for persistent headaches. Prefers morning slot.",
                "appointment_details": {
                    "doctor_id": "doctor-uuid-123",
                    "slot_time": "10:30",
                    "severity": "medium",
                    "enhanced_description": "Patient experiencing persistent headaches for 3 days with mild nausea."
                },
                "confidence_score": 0.95,
                "missing_information": []
            }
        }

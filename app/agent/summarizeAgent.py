"""
Appointment Summarize Agent
AI agent that analyzes patient descriptions and suggests appointment details
"""
import os
from typing import Optional
from datetime import date, datetime
from sqlalchemy.ext.asyncio import AsyncSession
import google.generativeai as genai


from app.agent.Tools.doctorTools import get_doctors_with_availability
from app.agent.Basemodels.summarizeModel import AppointmentSummary, ConversationSummary
from app.core.config import settings

class AppointmentAgent:
    """
    AI Agent for analyzing patient descriptions and suggesting appointments.
    Uses Google Gemini to understand symptoms and match with appropriate doctors.
    """
    
    def __init__(self):
        genai.configure(api_key="AIzaSyD0sWYRnnfSNHUKa37FId8HgH3dCGItPSo")
        self.model_name = settings.GENERAL_MODEL
    
    async def analyze_and_suggest_appointment(
        self,
        description: str,
        hospital_id: str,
        appointment_date: date,
        db: AsyncSession,
        patient_id: Optional[str] = None
    ) -> AppointmentSummary:
        """
        Analyze patient description and suggest appointment details.
        
        Args:
            description: Patient's description of symptoms/reason for visit
            hospital_id: Hospital ID to search for doctors
            appointment_date: Date for the appointment
            db: Database session
            patient_id: Optional patient ID
        
        Returns:
            AppointmentSummary with doctor_id, slot_time, severity, enhanced_description
        """
        
        # Get available doctors from the hospital
        doctors = await get_doctors_with_availability(
            hospital_id=hospital_id,
            db=db,
            target_date=appointment_date
        )
        
        if not doctors:
            raise ValueError("No doctors available at this hospital")
        
        # Prepare doctor information for the AI
        doctor_info = self._format_doctor_info(doctors)
        
        # Create prompt for Gemini
        prompt = self._create_analysis_prompt(description, doctor_info, appointment_date)
        
        # Call Gemini API with structured output
        model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={
                "temperature": 0.3,
                "response_mime_type": "application/json"
            }
        )
        response = model.generate_content(prompt)
        
        # Parse the structured response
        import json
        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse AI response as JSON: {response.text}") from e
        
        # Validate required fields (check for both missing keys and None values)
        required_fields = ["doctor_id", "severity", "enhanced_description"]
        missing_fields = [field for field in required_fields if not result.get(field)]
        
        if missing_fields:
            raise ValueError(
                f"AI response missing or null for required fields: {', '.join(missing_fields)}. "
                f"Full response: {result}"
            )
        
        # Handle slot_time - if AI returns null, select intelligently based on severity
        slot_time = result.get("slot_time")
        if not slot_time:
            # Find the doctor to get their available slots
            selected_doctor = None
            for doctor in doctors:
                if doctor["doctor_id"] == result["doctor_id"]:
                    selected_doctor = doctor
                    break
            
            if selected_doctor and selected_doctor.get("available_slots"):
                severity = result["severity"].lower()
                available_slots = selected_doctor["available_slots"]
                
                # For high/critical: pick earliest slot
                # For low/medium: pick first available
                if severity in ["high", "critical"]:
                    slot_time = available_slots[0]  # First/earliest slot
                else:
                    slot_time = available_slots[0]  # Any available slot
            else:
                raise ValueError(
                    f"AI did not provide slot_time and no fallback slots available for doctor {result['doctor_id']}"
                )
        
        # Create AppointmentSummary object
        appointment_summary = AppointmentSummary(
            doctor_id=result["doctor_id"],
            slot_time=slot_time,  # Use validated/fallback slot_time
            severity=result["severity"],
            enhanced_description=result["enhanced_description"],
            appointment_date=appointment_date,
            patient_id=patient_id
        )
        
        return appointment_summary
    
    def _format_doctor_info(self, doctors: list) -> str:
        """Format doctor information for AI prompt."""
        info_lines = []
        for doctor in doctors:
            # Join slots into a comma-separated string, limiting to first 15 for brevity if needed
            available_slots = ", ".join(doctor["available_slots"][:15])  
            info_lines.append(
                f"- Doctor ID: {doctor['doctor_id']}\n"
                f"  Name: {doctor['name']}\n"
                f"  Specialization: {doctor['specialization']}\n"
                f"  Experience: {doctor['experience_years']} years\n"
                f"  Available Slots: {available_slots}\n"
                f"  Free Slots Count: {doctor['free_count']}"
            )
        return "\n\n".join(info_lines)
    
    def _create_analysis_prompt(
        self, 
        description: str, 
        doctor_info: str,
        appointment_date: date
    ) -> str:
        """Create prompt for Gemini analysis."""
        return f"""You are a medical appointment assistant. Analyze the patient's description and suggest the most appropriate doctor and appointment details.

Patient Description:
{description}

Appointment Date: {appointment_date}

Available Doctors:
{doctor_info}

Instructions:
1. Analyze the symptoms/condition described
2. Match with the most appropriate doctor based on specialization
3. SELECT A TIME SLOT based on severity:
   - For HIGH or CRITICAL severity: Pick the EARLIEST available slot from the doctor's available slots
   - For LOW or MEDIUM severity: Pick any available slot within the next 1-2 hours
   - IMPORTANT: You MUST pick an actual slot from the "Available Slots" list shown above
   - DO NOT return null or empty string for slot_time
4. Determine severity level (low, medium, high, critical) based on:
   - low: routine checkups, minor issues
   - medium: persistent symptoms, moderate concerns (e.g., fever for 3 days)
   - high: severe symptoms, urgent but not life-threatening
   - critical: emergency situations, severe pain, life-threatening
5. Create an enhanced description that summarizes the condition professionally

CRITICAL RULES:
- ALL fields are REQUIRED and MUST NOT be null or empty
- slot_time MUST be a valid HH:MM format from the available slots list
- severity MUST be exactly one of: low, medium, high, critical

Response Format (strict JSON):
{{
  "doctor_id": "string (exact ID from the available doctors list)",
  "slot_time": "string (HH:MM format, e.g., '10:30' - MUST be from available slots)",
  "severity": "string (one of: low, medium, high, critical)",
  "enhanced_description": "string (professional summary, minimum 10 characters)"
}}

Example for medium severity (fever):
{{
  "doctor_id": "abc-123",
  "slot_time": "14:00",
  "severity": "medium",
  "enhanced_description": "Patient presenting with fever persisting for 3 days. Requires medical evaluation for potential infection."
}}

Example for high severity (severe pain):
{{
  "doctor_id": "xyz-789",
  "slot_time": "09:00",
  "severity": "high",
  "enhanced_description": "Patient experiencing severe abdominal pain. Urgent medical attention required."
}}
"""


async def create_appointment_suggestion(
    description: str,
    hospital_id: str,
    db: AsyncSession,
    appointment_date: Optional[date] = None,
    patient_id: Optional[str] = None
) -> AppointmentSummary:
    """
    Convenience function to create appointment suggestion.
    
    Args:
        description: Patient's description
        hospital_id: Hospital ID
        db: Database session
        appointment_date: Date for appointment (defaults to today)
        patient_id: Optional patient ID
    
    Returns:
        AppointmentSummary with suggested appointment details
    """
    if appointment_date is None:
        appointment_date = date.today()
    
    agent = AppointmentAgent()
    return await agent.analyze_and_suggest_appointment(
        description=description,
        hospital_id=hospital_id,
        appointment_date=appointment_date,
        db=db,
        patient_id=patient_id
    )
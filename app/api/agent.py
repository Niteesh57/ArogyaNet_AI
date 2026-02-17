"""
AI Agent API Endpoints
Provides endpoints for AI-powered appointment suggestions
"""
from typing import Any, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api import deps
from app.models.user import User
from app.agent.summarizeAgent import create_appointment_suggestion
from app.agent.Basemodels.summarizeModel import AppointmentSummary

router = APIRouter()


class AppointmentSuggestionRequest(BaseModel):
    """Request model for appointment suggestion"""
    description: str
    appointment_date: Optional[date] = None
    patient_id: Optional[str] = None
    hospital_id: Optional[str] = None


@router.post("/suggest-appointment", response_model=AppointmentSummary)
async def suggest_appointment(
    *,
    db: AsyncSession = Depends(deps.get_db),
    request: AppointmentSuggestionRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    AI-powered appointment suggestion.
    
    - Takes patient description and date
    - Analyzes symptoms using AI
    - Suggests appropriate doctor based on specialization
    - Recommends time slot from available slots
    - Determines severity level
    - Returns structured appointment data
    
    **Requires:** GEMINI_API_KEY environment variable
    """
    target_hospital_id = request.hospital_id or current_user.hospital_id
    
    if not target_hospital_id:
        raise HTTPException(
            status_code=400, 
            detail="Hospital ID must be provided either in request or user profile"
        )
    
    try:
        suggestion = await create_appointment_suggestion(
            description=request.description,
            hospital_id=target_hospital_id,
            db=db,
            appointment_date=request.appointment_date,
            patient_id=request.patient_id
        )
        return suggestion
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate appointment suggestion: {str(e)}"
        )

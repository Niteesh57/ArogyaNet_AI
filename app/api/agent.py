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
from app.utils.voice_trigger import trigger_call

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


class DocAnalysisRequest(BaseModel):
    document_url: str
    question: str
    appointment_id: Optional[str] = None

from app.agent.docAgent import analyze_medical_document
from typing import List
from app.models.appointment_chat import ChatResponse, AppointmentChat
from sqlalchemy import select

@router.post("/analyze", response_model=dict)
async def analyze_report(
    request: DocAnalysisRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Analyze a medical document (PDF or Image) using MedGemma.
    - Extracts text from PDF or loads image.
    - Uses VQA agent to answer the question.
    - Maintains conversation context per user.
    - Saves chat history if appointment_id is provided.
    """
    try:
        response = await analyze_medical_document(
            user_id=current_user.id,
            document_url=request.document_url,
            question=request.question,
            appointment_id=request.appointment_id,
            db=db
        )
        return {"answer": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/appointments/{appointment_id}/chat", response_model=List[ChatResponse])
async def get_appointment_chat_history(
    appointment_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Get chat history for a specific appointment.
    """
    # Authorization check: User must be related to appointment (patient) or be a doctor (or admin)
    # Ideally should check appointment ownership. For now, assuming basic access.
    
    query = select(AppointmentChat).where(AppointmentChat.appointment_id == appointment_id).order_by(AppointmentChat.created_at)
    result = await db.execute(query)
    chats = result.scalars().all()
    return chats


class CallTriggerRequest(BaseModel):
    phone_number: str


@router.post("/trigger-call")
async def trigger_outbound_call(
    request: CallTriggerRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Triggers an outbound call to the specified phone number using LiveKit SIP.
    """
    try:
        await trigger_call(request.phone_number)
        return {"message": f"Call initiated to {request.phone_number}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


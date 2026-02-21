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

from fastapi.responses import StreamingResponse

@router.post("/analyze")
async def analyze_report(
    request: DocAnalysisRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Analyze a medical document using MedGemma (Streaming).
    """
    try:
        stream = analyze_medical_document(
            user_id=current_user.id,
            document_url=request.document_url,
            question=request.question,
            appointment_id=request.appointment_id,
            db=db
        )
        return StreamingResponse(stream, media_type="text/plain")
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
    appointment_id: Optional[str] = None


@router.post("/trigger-call")
async def trigger_outbound_call(
    request: CallTriggerRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Triggers an outbound call to the specified phone number using LiveKit SIP.
    """
    try:
        await trigger_call(request.phone_number, request.appointment_id)
        return {"message": f"Call initiated to {request.phone_number}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DeepResearchRequest(BaseModel):
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    pdf_url: Optional[str] = None
    vision_prompt: Optional[str] = None

from app.agent.deepAgent import run_deep_research

@router.post("/deep-research")
async def deep_research_endpoint(
    request: DeepResearchRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Multimodal Deep Research Agent (Streaming).
    Returns a stream of JSON events:
    - {"type": "status", "message": "..."}
    - {"type": "token", "content": "..."}
    """
    try:
        stream = run_deep_research(
            image_url=request.image_url,
            audio_url=request.audio_url,
            pdf_url=request.pdf_url,
            vision_prompt=request.vision_prompt
        )
        # Using text/event-stream for SSE compatibility
        return StreamingResponse(stream, media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ExpertCheckRequest(BaseModel):
    check_text: str
    category: str
    hospital_id: Optional[str] = None
    medication: List[str] = []
    lab_test: List[str] = []

from app.agent.ExpAgent import upsert_check, retrieve_checks
import uuid

@router.post("/expert-check")
async def add_expert_check(
    request: ExpertCheckRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Store a senior doctor's insight/check into the knowledge base (Pinecone).
    """
    try:
        # Use provided hospital_id or fallback to user's hospital
        hospital_id = request.hospital_id or current_user.hospital_id
        if not hospital_id:
             raise HTTPException(status_code=400, detail="Hospital ID required")

        check_id = str(uuid.uuid4())
        
        # Convert lists to strings for embedding/metadata
        medication_str = ", ".join(request.medication) if request.medication else ""
        lab_test_str = ", ".join(request.lab_test) if request.lab_test else ""
        
        result = await upsert_check(
            check_id=check_id,
            check_text=request.check_text,
            category=request.category,
            hospital_id=hospital_id,
            medication=medication_str,
            lab_test=lab_test_str
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expert-check", response_model=List[dict])
async def search_expert_checks(
    query: str,
    category: Optional[str] = None,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Search for expert insights/checks.
    """
    try:
        hospital_id = current_user.hospital_id
        if not hospital_id:
             raise HTTPException(status_code=400, detail="User must belong to a hospital")
             
        results = await retrieve_checks(
            query=query,
            hospital_id=hospital_id,
            user_hospital_id=hospital_id, # Must match
            category=category
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExpertChatRequest(BaseModel):
    query: str
    category: Optional[str] = None
    hospital_id: Optional[str] = None # Allow strict filtering override

from app.agent.ExpAgent import stream_expert_answer

@router.post("/expert-chat")
async def expert_chat_endpoint(
    request: ExpertChatRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Stream an expert medical answer based on the knowledge base.
    Uses GENERAL_MODEL + Pinecone Context.
    Returns: Server-Sent Events (SSE).
    """
    # 1. Determine Hospital ID and Filtering Logic
    if request.hospital_id:
        # Explicit override -> Search ONLY this hospital (Strict)
        target_hospital_id = request.hospital_id
        strict_mode = True
        # Only show sensitive data if it matches user's hospital
        user_verification_id = current_user.hospital_id 
    else:
        # Default -> User's hospital, with fallback to Global (Not Strict)
        target_hospital_id = current_user.hospital_id
        strict_mode = False
        # Valid use case: Implicit search should NOT show detailed meds/labs (Summary Mode)
        user_verification_id = "HIDDEN" 
        
    if not target_hospital_id:
        raise HTTPException(status_code=400, detail="User must belong to a hospital or provide hospital_id")
        
    try:
        stream = stream_expert_answer(
            query=request.query,
            hospital_id=target_hospital_id,
            user_hospital_id=user_verification_id,
            category=request.category,
            strict_hospital=strict_mode
        )
        return StreamingResponse(stream, media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DietPlannerRequest(BaseModel):
    appointment_id: str
    patient_problem: str
    doctor_remarks: str

from app.agent.dietPlannerAgent import stream_diet_plan

@router.post("/diet-planner")
async def diet_planner_endpoint(
    request: DietPlannerRequest,
    current_user: User = Depends(deps.get_current_doctor),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Generate and stream a diet plan for a patient based on their health problem and doctor's remarks.
    Only accessible by users with the DOCTOR role.
    Returns: Server-Sent Events (SSE).
    """
    try:
        stream = stream_diet_plan(
            appointment_id=request.appointment_id,
            patient_problem=request.patient_problem,
            doctor_remarks=request.doctor_remarks,
            db=db
        )
        return StreamingResponse(stream, media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class EventDataPopulatorRequest(BaseModel):
    image_url: str
    keys: List[str]

from app.agent.eventDataPopulator import populate_event_data

@router.post("/populate-event-data")
async def populate_event_data_endpoint(
    request: EventDataPopulatorRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Extract structured data from an image based on provided keys.
    Returns a JSON object with extracted values.
    """
    try:
        result = await populate_event_data(
            image_url=request.image_url,
            keys=request.keys
        )
        if "error" in result:
             raise HTTPException(status_code=500, detail=result["error"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MedicalSummarizeRequest(BaseModel):
    image_url: str

from app.agent.medicalSummarizer import stream_medical_summary

@router.post("/summarize-medical-report")
async def summarize_medical_report_endpoint(
    request: MedicalSummarizeRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Summarize a medical report or prescription image.
    Returns: Server-Sent Events (SSE).
    """
    try:
        stream = stream_medical_summary(image_url=request.image_url)
        return StreamingResponse(stream, media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

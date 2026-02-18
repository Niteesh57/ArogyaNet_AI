from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from app.api import deps
from app.models import document
from app.schemas import document as doc_schema
from app.utils.file import upload_file_to_supabase
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/upload", response_model=doc_schema.Document)
async def upload_document(
    title: str = Form(...),
    appointment_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Upload a document (PDF, Image, etc) for the current user.
    Optionally link to an appointment.
    """
    logger.info(f"Uploading document '{title}' for user {current_user.id}")
    
    # 1. Upload to Supabase
    try:
        # We use default bucket ("images") or create a new one "documents" if user wants.
        # For now, sticking to logic in utils/file.py which uses settings.SUPABASE_BUCKET
        file_url = await upload_file_to_supabase(file)
    except Exception as e:
        logger.error(f"Supabase upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to storage")

    # 1.5 Fetch Appointment details if provided
    db_appt = None
    patient_id = None
    doctor_id = None
    
    if appointment_id:
        from app.crud.appointment import appointment as crud_appointment
        db_appt = await crud_appointment.get(db, id=appointment_id)
        if db_appt:
            patient_id = db_appt.patient_id
            doctor_id = db_appt.doctor_id

    # 2. Create DB Entry
    db_doc = document.Document(
        title=title,
        file_url=file_url,
        file_type=file.content_type,
        user_id=current_user.id,
        appointment_id=appointment_id,
        patient_id=patient_id,
        doctor_id=doctor_id
    )
    db.add(db_doc)
    await db.commit()
    await db.refresh(db_doc)
    
    return db_doc

@router.get("/my-documents", response_model=List[doc_schema.Document])
async def get_my_documents(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
): 
    """
    List all documents uploaded by the current user.
    """
    result = await db.execute(select(document.Document).filter(document.Document.user_id == current_user.id))
    return result.scalars().all()

@router.get("/appointment/{appointment_id}", response_model=List[doc_schema.Document])
async def get_appointment_documents(
    appointment_id: str, # UUID string
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    List all documents linked to a specific appointment.
    """
    # Verify user has access to this appointment? (Ideally yes, but for now assuming if they have ID they can see docs)
    # Filter by appointment_id
    query = select(document.Document).where(document.Document.appointment_id == appointment_id).order_by(document.Document.created_at.desc())
    result = await db.execute(query)
    docs = result.scalars().all()
    return docs

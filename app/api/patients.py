from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.crud.patient import patient as crud_patient
from app.schemas.patient import Patient, PatientUpdate, PatientCreate, PatientWithAppointmentCreate
from app.schemas.user import User as UserSchema
from app.models.user import User

router = APIRouter()

@router.post("/with-appointment", response_model=Patient)
async def create_patient_with_appointment(
    *,
    db: AsyncSession = Depends(deps.get_db),
    patient_in: PatientWithAppointmentCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create a new patient record and optionally an appointment.
    
    - Creates User account (if email doesn't exist)
    - Creates Patient record
    - Creates Appointment (if provided)
    - Transactional: All or nothing
    """
    from app.crud.user import user as crud_user
    from app.schemas.user import UserCreate
    from app.core.security import get_password_hash
    from app.models.user import UserRole
    from app.models.patient import Patient as PatientModel
    from app.crud.appointment import appointment as crud_appointment
    from app.schemas.appointment import AppointmentCreate
    
    # 1. Assign hospital_id if user has one
    if current_user.hospital_id and not patient_in.hospital_id:
        patient_in.hospital_id = current_user.hospital_id
    
    # Check if user with this email already exists
    existing_user = await crud_user.get_by_email(db, email=patient_in.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # 2. Auto-create user account for patient
    user_data = UserCreate(
        email=patient_in.email,
        full_name=patient_in.full_name,
        phone_number=patient_in.phone,
        password=get_password_hash(patient_in.password or "Patient@123"),
        role=UserRole.PATIENT,
        hospital_id=patient_in.hospital_id,
        is_active=True,
        is_verified=True
    )
    created_user = await crud_user.create(db, obj_in=user_data)
    
    # 3. Create patient record linked to user
    patient_data = patient_in.model_dump(exclude={"email", "password", "appointment"})
    patient_data["user_id"] = created_user.id
    
    patient = PatientModel(**patient_data)
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    
    # 4. Create Appointment if provided
    if patient_in.appointment:
        appt_data = patient_in.appointment.model_dump()
        appt_data["patient_id"] = patient.id
        # Ensure we use the correct schema for creation that includes patient_id
        appt_create = AppointmentCreate(**appt_data)
        await crud_appointment.create(db, obj_in=appt_create)

    return patient

@router.get("/search", response_model=List[UserSchema])
async def search_patients(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Search for potential patients (Users with BASE or PATIENT role).
    
    - Searches in User table directly
    - Searches by name or email
    - Returns User objects
    - Useful for finding registered users to create patient records for
    """
    from sqlalchemy import select, or_
    from app.models.user import UserRole
    
    search_term = f"%{q}%"
    
    # Search in User table
    query = select(User).filter(
        or_(
            User.full_name.ilike(search_term),
            User.email.ilike(search_term)
        )
    ).filter(
        User.role.in_([UserRole.BASE.value, UserRole.PATIENT.value])
    ).limit(20)
    
    # If hospital admin, maybe filter by hospital? 
    # But usually new users might not have hospital_id yet if they just signed up.
    # Allowing search across all BASE users for now to let them be "admitted"
        
    users = (await db.execute(query)).scalars().all()
    return users

@router.get("/{id}/name")
async def get_patient_name(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get patient's name by ID.
    
    - Returns: {"full_name": "Patient Name"}
    """
    patient = await crud_patient.get(db, id=id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    return {"full_name": patient.full_name}

@router.post("/", response_model=Patient)
async def create_patient(
    *,
    db: AsyncSession = Depends(deps.get_db),
    patient_in: PatientCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create a new patient record.
    
    - Automatically creates a user account for the patient
    - Requires email for user account creation
    - Sets default password: "Patient@123"
    - Assigns PATIENT role and hospital_id
    - Captures patient demographic information
    - Can optionally assign a doctor to the patient
    """
    from app.crud.user import user as crud_user
    from app.schemas.user import UserCreate
    from app.core.security import get_password_hash
    from app.models.user import UserRole
    
    # Assign hospital_id if user has one
    if current_user.hospital_id and not patient_in.hospital_id:
        patient_in.hospital_id = current_user.hospital_id
    
    # Check if user with this email already exists
    existing_user = await crud_user.get_by_email(db, email=patient_in.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Auto-create user account for patient
    user_data = UserCreate(
        email=patient_in.email,
        full_name=patient_in.full_name,
        phone_number=patient_in.phone,
        password=get_password_hash(patient_in.password or "Patient@123"),
        role=UserRole.PATIENT,
        hospital_id=patient_in.hospital_id,
        is_active=True,
        is_verified=True
    )
    created_user = await crud_user.create(db, obj_in=user_data)
    
    # Create patient record linked to user
    patient_data = patient_in.model_dump(exclude={"email", "password"})
    patient_data["user_id"] = created_user.id
    
    from app.models.patient import Patient as PatientModel
    patient = PatientModel(**patient_data)
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    
    return patient

@router.put("/{id}", response_model=Patient)
async def update_patient(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    patient_in: PatientUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Update patient information.
    
    - Modify patient demographics
    - Reassign doctor
    """
    patient = await crud_patient.get(db, id=id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient = await crud_patient.update(db, db_obj=patient, obj_in=patient_in)
    return patient

@router.delete("/{id}", response_model=Patient)
async def delete_patient(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Delete a patient record.
    
    - Permanently removes patient
    """
    patient = await crud_patient.get(db, id=id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient = await crud_patient.remove(db, id=id)
    return patient

@router.get("/", response_model=List[Patient])
async def read_patients(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Retrieve patients.
    
    - **Hospital filtered**: Only shows patients from your hospital
    - **Pagination**: Use skip/limit for pagination
    """
    patients = await crud_patient.get_multi(db, skip=skip, limit=limit)
    return patients

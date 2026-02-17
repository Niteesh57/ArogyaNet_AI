from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.crud.appointment import appointment as crud_appointment
from app.schemas.appointment import Appointment, AppointmentCreate, AppointmentUpdate, AppointmentWithDoctor, AppointmentRemarks
from app.models.user import User
from app.crud.patient import patient as crud_patient
from app.crud.doctor import doctor as crud_doctor
from app.models.user import UserRole
from app.schemas.hospital import Hospital
from datetime import date

router = APIRouter()

@router.post("/{id}/consultation", response_model=Appointment)
async def consultation_update(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    remarks_in: AppointmentRemarks,
    severity: Optional[str] = None, # Should match SeverityLevel enum value
    status: Optional[str] = None, # Should match AppointmentStatus enum value
    next_followup: Optional[date] = None,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Doctor Consultation Endpoint.
    
    - Add remarks (text, medicine, lab)
    - Update severity
    - Update status (started, in_progress, finished, admitted)
    - Set next follow-up date
    """
    # 1. Verify Doctor
    doctor_profile = await crud_doctor.get_by_user_id(db, user_id=current_user.id)
    if not doctor_profile:
        raise HTTPException(status_code=403, detail="Only doctors can perform consultations")
    
    # 2. Get Appointment
    appointment = await crud_appointment.get(db, id=id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    # 3. Verify Ownership (Doctor owns this appointment)
    if appointment.doctor_id != doctor_profile.id:
         raise HTTPException(status_code=403, detail="You are not assigned to this appointment")

    # 4. Update fields
    update_data = {}
    if remarks_in:
        # Convert Pydantic model to dict (or JSON compatible format)
        update_data["remarks"] = remarks_in.model_dump()
        
    if severity:
        update_data["severity"] = severity

    if status:
        update_data["status"] = status
        
    if next_followup:
        update_data["next_followup"] = next_followup
        
    appointment = await crud_appointment.update(db, db_obj=appointment, obj_in=update_data)
    return appointment

@router.post("/", response_model=Appointment)
async def create_appointment(
    *,
    db: AsyncSession = Depends(deps.get_db),
    appointment_in: AppointmentCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create a new appointment.
    
    - **Patients**: Can create appointments for themselves.
    - **Admins**: Can create appointments for anyone.
    """
    from app.crud.patient import patient as crud_patient
    from app.models.user import UserRole

    # If user is a patient, ensure they are booking for themselves
    if current_user.role == UserRole.PATIENT:
        # Get patient profile for current user
        patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
        if not patient_profile:
             raise HTTPException(status_code=400, detail="Patient profile not found for this user.")
        
        # Override patient_id with their own
        appointment_in.patient_id = patient_profile.id

    # Check slot availability
    # (Simplified check - ideally should reuse doctorTools logic or add similar check in CRUD)
    # For now relying on frontend/AI to pick valid slots or DB constraints if any
    
    appointment = await crud_appointment.create(db, obj_in=appointment_in)
    return appointment

@router.get("/patient/{patient_id}", response_model=List[AppointmentWithDoctor])
async def read_patient_appointments(
    *,
    db: AsyncSession = Depends(deps.get_db),
    patient_id: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get all appointments for a specific patient.
    
    - Returns appointment details + doctor name/specialization.
    - **Patients**: Can only view their own appointments.
    """
    from app.crud.patient import patient as crud_patient
    from app.models.user import UserRole
    from app.schemas.hospital import Hospital
    
    # Ownership check
    # Ownership check
    if current_user.role == UserRole.PATIENT:
        patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
        
        if not patient_profile:
             raise HTTPException(status_code=403, detail="No patient profile found for this user")

        # Allow user to pass either their Patient ID OR their User ID
        # If they passed User ID, we use the Patient ID from profile
        if patient_id == str(current_user.id):
             patient_id = patient_profile.id
        elif patient_profile.id != patient_id:
            expected = patient_profile.id
            raise HTTPException(status_code=403, detail=f"Not authorized. You are logged in as patient {expected}, but requested data for {patient_id}. Try using your Patient ID or just your User ID.")

    appointments = await crud_appointment.get_by_patient(db, patient_id=patient_id)
    
    # ... logic for response mapping ...
    return await _map_appointments(appointments)

@router.get("/my-appointments", response_model=List[AppointmentWithDoctor])
async def read_my_appointments(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get all appointments for the current logged-in patient.
    """
    from app.crud.patient import patient as crud_patient
    from app.models.user import UserRole
    
    if current_user.role != UserRole.PATIENT:
         raise HTTPException(status_code=400, detail="Only patients can access this endpoint")
         
    patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
    if not patient_profile:
        raise HTTPException(status_code=404, detail="Patient profile not found for current user")
        
    appointments = await crud_appointment.get_by_patient(db, patient_id=patient_profile.id)
    return await _map_appointments(appointments)

async def _map_appointments(appointments):
    
    # Map to schema with doctor details
    result = []
    for appt in appointments:
        doctor_name = "Unknown"
        doctor_spec = None
        hospital_name = None
        hospital_obj = None
        
        if appt.doctor:
            if appt.doctor.user:
                doctor_name = appt.doctor.user.full_name
            doctor_spec = appt.doctor.specialization
            if appt.doctor.hospital:
                hospital_name = appt.doctor.hospital.name
                hospital_obj = appt.doctor.hospital
                
        # Create response object
        appt_dict = AppointmentWithDoctor.model_validate(appt)
        
        # Populate flat fields
        appt_dict.doctor_name = doctor_name
        appt_dict.doctor_specialization = doctor_spec
        appt_dict.hospital_name = hospital_name
        
        # Populate nested objects
        # doctor should be populated automatically by model_validate from appt.doctor relationship
        # hospital needs manual assignment from appt.doctor.hospital
        if hospital_obj:
            appt_dict.hospital = Hospital.model_validate(hospital_obj)
            
        result.append(appt_dict)
        
    return result

@router.get("/", response_model=List[Appointment])
async def read_appointments(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get list of appointments.
    """
    appointments = await crud_appointment.get_multi(db, skip=skip, limit=limit)
    return appointments

@router.get("/{id}", response_model=Appointment)
async def read_appointment(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get appointment details by ID.
    """
    appointment = await crud_appointment.get(db, id=id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Check access for patient
    from app.models.user import UserRole
    from app.crud.patient import patient as crud_patient
    if current_user.role == UserRole.PATIENT:
        patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
        if not patient_profile or appointment.patient_id != patient_profile.id:
             raise HTTPException(status_code=403, detail="Not authorized")

    return appointment

@router.put("/{id}", response_model=Appointment)
async def update_appointment(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    appointment_in: AppointmentUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Update appointment.
    """
    appointment = await crud_appointment.get(db, id=id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Check access for patient
    from app.models.user import UserRole
    from app.crud.patient import patient as crud_patient
    if current_user.role == UserRole.PATIENT:
        patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
        if not patient_profile or appointment.patient_id != patient_profile.id:
             raise HTTPException(status_code=403, detail="Not authorized to edit this appointment")

    appointment = await crud_appointment.update(db, db_obj=appointment, obj_in=appointment_in)
    return appointment

@router.delete("/{id}", response_model=Appointment)
async def delete_appointment(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Cancel/delete appointment.
    """
    appointment = await crud_appointment.get(db, id=id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Check access for patient
    from app.models.user import UserRole
    from app.crud.patient import patient as crud_patient
    if current_user.role == UserRole.PATIENT:
        patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
        if not patient_profile or appointment.patient_id != patient_profile.id:
             raise HTTPException(status_code=403, detail="Not authorized to cancel this appointment")

    appointment = await crud_appointment.remove(db, id=id)
    return appointment

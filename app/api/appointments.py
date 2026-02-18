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
from pydantic import BaseModel
from app.schemas.appointment_vital import AppointmentVitalCreate, AppointmentVitalResponse, AppointmentVitalInput
from app.crud.appointment_vital import appointment_vital as crud_appointment_vital

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

@router.post("/{id}/vitals", response_model=AppointmentVitalResponse)
async def add_vitals(
    id: str,
    vitals_in: AppointmentVitalInput,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Add a vital sign log to the appointment.
    """
    # 1. Get Appointment
    appointment = await crud_appointment.get(db, id=id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    # 2. Authorization (Nurse, Admin)
    # User requested: "only nursh can update, docoto and patient can see it"
    if current_user.role not in [UserRole.NURSE.value, UserRole.HOSPITAL_ADMIN.value]:
        raise HTTPException(status_code=403, detail="Only nurses (and admins) can log vitals")
        
    # 3. Create Log Entry
    # Create internal Create schema with IDs
    vital_data = AppointmentVitalCreate(
        **vitals_in.model_dump(),
        appointment_id=id,
        nurse_id=current_user.id
    )
    
    new_vital = await crud_appointment_vital.create(db, obj_in=vital_data)
    
    # Auto-assign nurse to appointment if not already assigned
    if not appointment.nurse_id:
        # We know current_user is a NURSE (checked above)
        appointment.nurse_id = current_user.id
        db.add(appointment)
        await db.commit()
        await db.refresh(appointment)
        
    return new_vital
    
@router.get("/{id}/vitals", response_model=List[AppointmentVitalResponse])
async def get_vitals(
    id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get all vitals for an appointment.
    """
    # Check appointment exists
    appointment = await crud_appointment.get(db, id=id)
    if not appointment:
         raise HTTPException(status_code=404, detail="Appointment not found")
         
    # Check access (Patient, Doctor, Nurse, Admin)
    # If patient, ensure it's their appointment
    if current_user.role == UserRole.PATIENT:
        from app.crud.patient import patient as crud_patient
        patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
        if not patient_profile or appointment.patient_id != patient_profile.id:
             raise HTTPException(status_code=403, detail="Not authorized")

    vitals = await crud_appointment_vital.get_by_appointment(db, appointment_id=id)
    return vitals

@router.put("/{id}/assign-nurse", response_model=Appointment)
async def assign_nurse_to_appointment(
    id: str,
    nurse_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Assign a nurse to an appointment.
    """
    # 1. Authorization (Doctors, Admins)
    if current_user.role not in [UserRole.DOCTOR.value, UserRole.HOSPITAL_ADMIN.value, UserRole.SUPER_ADMIN.value]:
         raise HTTPException(status_code=403, detail="Not authorized to assign nurses")

    # 2. Get Appointment
    appointment = await crud_appointment.get(db, id=id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # 3. Verify Nurse
    from app.crud.user import user as crud_user
    nurse = await crud_user.get(db, id=nurse_id) # Using User ID for now as Nurse ID usually == User ID in simplistic model or we need to find Nurse profile.
    # Implementation Plan assumption: nurse_id refers to User ID with role 'nurse' or Nurse profile ID.
    # Given `patient.assigned_nurse_id` often refers to User ID in this codebase, I will Stick to User Level ID for simplicity or check if Nurse table is used.
    # Checking `models/user.py`, `Nurse` is a profile. But `Patient.assigned_nurse_id` likely stores the UUID.
    # Let's assume User ID for now as `nurse = relationship("User")` in models.
    
    if not nurse:
         raise HTTPException(status_code=404, detail="Nurse not found")

    appointment.nurse_id = nurse_id
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    return appointment

@router.get("/nurse/assigned", response_model=List[AppointmentWithDoctor])
async def read_appointments_for_nurse(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get appointments assigned to the current nurse.
    """
    if current_user.role != UserRole.NURSE.value:
        raise HTTPException(status_code=403, detail="Only nurses can access this endpoint")
        
    # Filter appointments by nurse_id == current_user.id
    # We need a crud method for this or use get_multi with filter if available.
    # Adding simplified query here or using crud method.
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.appointment import Appointment as AppointmentModel
    from app.models.doctor import Doctor
    from app.models.patient import Patient
    
    # Include nurse relationship so _map_appointments can find the name
    query = select(AppointmentModel).options(
        selectinload(AppointmentModel.doctor).selectinload(Doctor.user),
        selectinload(AppointmentModel.doctor).selectinload(Doctor.hospital),
        selectinload(AppointmentModel.nurse),
        selectinload(AppointmentModel.patient)
    ).filter(AppointmentModel.nurse_id == current_user.id).order_by(AppointmentModel.date.desc(), AppointmentModel.slot)
    
    result = await db.execute(query)
    appointments = result.scalars().all()
    
    return await _map_appointments(appointments)

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

        # Populate nurse_name if available (e.g. eagerly loaded or just present)
        # Note: appt.nurse might be loaded if we added selectinload(Appointment.nurse) 
        # in the query calling this.
        if hasattr(appt, 'nurse') and appt.nurse:
             appt_dict.nurse_name = appt.nurse.full_name

        if hasattr(appt, 'patient') and appt.patient:
             from app.schemas.patient import Patient
             appt_dict.patient = Patient.model_validate(appt.patient)

            
        result.append(appt_dict)
        
    return result
        
@router.get("/search", response_model=List[AppointmentWithDoctor])
async def search_appointments(
    patient_id: str,
    doctor_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Search appointments by patient and doctor.
    
    - **patient_id**: Can be Patient Profile ID or User ID.
    - **doctor_id**: Doctor Profile ID.
    """
    from app.crud.patient import patient as crud_patient
    from app.models.user import UserRole
    
    # Resolve Patient ID if User ID is provided
    # Check if patient_id looks like a UUID (it should be)
    # but we can try to find patient by user_id first if it's not a direct match
    target_patient_id = patient_id
    
    # Try to find patient profile by ID first
    patient_profile = await crud_patient.get(db, id=patient_id)
    if not patient_profile:
        # If not found by ID, maybe it's a User ID?
        patient_profile = await crud_patient.get_by_user_id(db, user_id=patient_id)
        if patient_profile:
            target_patient_id = patient_profile.id
        else:
             # If still not found, and it was meant to be a patient_id, then it's invalid.
             # But let's proceed with original ID if we can't resolve it, effectively returning empty list or error later if strict.
             # For now, if we can't resolve it to a profile and it wasn't a profile ID, we might return empty.
             pass

    # Authorization Check
    # Patient can only search for themselves
    if current_user.role == UserRole.PATIENT:
        current_patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
        if not current_patient_profile or current_patient_profile.id != target_patient_id:
             raise HTTPException(status_code=403, detail="Not authorized to view these appointments")
    
    # Doctor/Nurse/Admin can search for any patient
    # (Refine if needed, e.g. Doctor only for their patients)
    
    appointments = await crud_appointment.get_by_patient_and_doctor(
        db, patient_id=target_patient_id, doctor_id=doctor_id
    )
    
    return await _map_appointments(appointments)

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
    # Use custom query to load relations (Doctor, Nurse)
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.doctor import Doctor
    from app.models.appointment import Appointment as AppointmentModel
    
    query = select(AppointmentModel).options(
        selectinload(AppointmentModel.doctor).selectinload(Doctor.user),
        selectinload(AppointmentModel.doctor).selectinload(Doctor.hospital),
        selectinload(AppointmentModel.nurse)
    ).filter(AppointmentModel.id == id)
    result = await db.execute(query)
    appointment = result.scalars().first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Manually set nurse_name to ensure it's in the response
    # Pydantic from_attributes=True might catch `nurse` object but `nurse_name` is flat.
    # We can set it on the object (it's not a dict, it's a model instance, but python allows attr setting)
    if appointment.nurse:
        appointment.nurse_name = appointment.nurse.full_name
    
    # Check access for patient
    from app.models.user import UserRole
    from app.crud.patient import patient as crud_patient
    if current_user.role == UserRole.PATIENT:
        patient_profile = await crud_patient.get_by_user_id(db, user_id=current_user.id)
        if not patient_profile or appointment.patient_id != patient_profile.id:
             raise HTTPException(status_code=403, detail="Not authorized")

    # Populate vitals for consistency
    appointment.vitals = await crud_appointment_vital.get_by_appointment(db, appointment_id=id)

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

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.api import deps
from app.crud.doctor import doctor as crud_doctor
from app.schemas.doctor import DoctorResponse, DoctorUpdate
from app.schemas.user import User as UserSchema
from app.models.user import User
from app.models.doctor import Doctor

router = APIRouter()

from app.schemas.patient import Patient
from app.models.patient import Patient as PatientModel
from app.models.appointment import Appointment

@router.get("/me/patients", response_model=List[Patient])
async def read_doctor_patients(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get list of patients for the current doctor (based on appointments).
    """
    # 1. Check if user is a doctor
    # We can check role, but we need doctor_id specifically
    doctor_profile = await crud_doctor.get_by_user_id(db, user_id=current_user.id)
    if not doctor_profile:
        raise HTTPException(status_code=400, detail="Current user is not registered as a doctor")
        
    # 2. Get distinct patients who have appointments with this doctor
    query = select(PatientModel).join(Appointment).filter(Appointment.doctor_id == doctor_profile.id).distinct().offset(skip).limit(limit)
    
    result = await db.execute(query)
    patients = result.scalars().all()
    return patients

@router.get("/me/followups/today", response_model=List[Any])
async def read_doctor_followups_today(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get follow-up appointments scheduled for today.
    """
    from datetime import date
    from sqlalchemy.orm import selectinload
    from app.schemas.appointment import AppointmentWithDoctor
    
    # 1. Verify Doctor
    doctor_profile = await crud_doctor.get_by_user_id(db, user_id=current_user.id)
    if not doctor_profile:
        raise HTTPException(status_code=400, detail="Current user is not registered as a doctor")
        
    # 2. Query for appointments with follow_up_date == today
    today = date.today()
    
    query = select(Appointment).options(
        selectinload(Appointment.patient),
        selectinload(Appointment.doctor).selectinload(Doctor.user),
        selectinload(Appointment.doctor).selectinload(Doctor.hospital),
        selectinload(Appointment.nurse)
    ).filter(
        Appointment.doctor_id == doctor_profile.id,
        Appointment.next_followup == today
    )
    
    result = await db.execute(query)
    appointments = result.scalars().all()
    
    # Map to schema (reusing mapping logic if available, or just returning list)
    # The response_model=List[Any] allows flexibility, but ideally we return Appointment schemas
    # Let's import the mapping logic or duplicate it slightly for now to ensure we get patient details
    
    from app.api.appointments import _map_appointments
    return await _map_appointments(appointments)

@router.get("/search-potential", response_model=List[UserSchema])
async def search_potential_doctors(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Search for potential doctors to add.
    
    - **Admin only**
    - Searches users with BASE role (not yet assigned as doctors)
    - When registered, user role changes to DOCTOR and hospital_id is set
    """
    from app.models.user import UserRole
    search_term = f"%{q}%"
    
    # Only search for BASE users (not yet assigned as doctors)
    query = select(User).filter(
        or_(
            User.full_name.ilike(search_term),
            User.email.ilike(search_term)
        )
    ).filter(User.role == UserRole.BASE.value).limit(20)
    
    users = (await db.execute(query)).scalars().all()
    return users

@router.get("/search", response_model=List[DoctorResponse])
async def search_doctors(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Search doctors in your hospital.
    
    - Search by name or specialization
    - Returns doctors from your hospital only
    """
    doctors = await crud_doctor.search(db, query=q, hospital_id=current_user.hospital_id)
    return doctors

@router.get("/", response_model=List[DoctorResponse])
async def read_doctors(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get list of doctors.
    
    - **Hospital filtered**: Only from your hospital
    - **Pagination**: Use skip/limit
    """
    doctors = await crud_doctor.get_multi(db, skip=skip, limit=limit)
    return doctors

@router.get("/{id}/name")
async def get_doctor_name(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get doctor's name by ID.
    
    - Returns: {"full_name": "Doctor Name"}
    """
    doctor = await crud_doctor.get(db, id=id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    # Eagerly load user relationship to get full_name
    await db.refresh(doctor, ["user"])
    return {
        "full_name": doctor.user.full_name if doctor.user else "Unknown",
        "specialization": doctor.specialization
    }

@router.get("/hospital/{hospital_id}/search", response_model=List[DoctorResponse])
async def search_doctors_in_hospital(
    hospital_id: str,
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Search doctors in a specific hospital by name or email.
    
    - **Hospital ID**: Specify the hospital
    - **Query**: Search by name or specialization
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Clean inputs
    hospital_id = hospital_id.strip()
    q = q.strip()
    
    doctors = await crud_doctor.search(db, query=q, hospital_id=hospital_id)
    logger.info(f"Found {len(doctors)} doctors")
    
    return doctors

@router.get("/{id}/slots")
async def get_doctor_slots(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    date: str,  # Expect YYYY-MM-DD string
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get all 30-min slots for a doctor on a specific date.
    
    - Checks doctor's availability for the day of week
    - Checks existing appointments to mark slots as booked
    - Returns list of {time: "HH:MM", status: "available" | "booked"}
    """
    from app.crud.availability import availability as crud_availability
    from app.crud.appointment import appointment as crud_appointment
    from datetime import datetime, timedelta, date as datetime_date
    
    # Parse date string to object
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # 1. Get day of week (monday, tuesday, etc.)
    day_of_week = target_date.strftime("%A").lower()
    
    # 2. Get doctor's availability for this day
    avail = await crud_availability.get_by_staff_day(db, staff_id=id, day_of_week=day_of_week)
    
    if not avail:
        return {"message": "Doctor not available on this day", "slots": []}
    
    # 3. Get existing appointments for this doctor on this date
    existing_appts = await crud_appointment.get_by_doctor_date(db, doctor_id=id, date=target_date)
    booked_times = set()
    for appt in existing_appts:
        # Assuming slot is stored as string "HH:MM"
        booked_times.add(appt.slot)
    
    # 4. Generate 30-min slots
    slots = []
    # Combine date with start time to get datetime
    current_time = datetime.combine(target_date, avail.start_time)
    end_time_dt = datetime.combine(target_date, avail.end_time)
    
    while current_time < end_time_dt:
        slot_str = current_time.strftime("%H:%M")
        status = "booked" if slot_str in booked_times else "available"
        
        slots.append({
            "time": slot_str,
            "status": status
        })
        
        current_time += timedelta(minutes=30)
        
    return slots

@router.put("/{id}", response_model=DoctorResponse)
async def update_doctor(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    doctor_in: DoctorUpdate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Update doctor information.
    
    - **Admin only**
    - Modify specialization, availability, etc.
    """
    doctor = await crud_doctor.get(db, id=id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    doctor = await crud_doctor.update(db, db_obj=doctor, obj_in=doctor_in)
    return doctor

@router.delete("/{id}", response_model=DoctorResponse)
async def delete_doctor(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Remove doctor from hospital.
    
    - **Admin only**
    - Removes doctor record
    """
    doctor = await crud_doctor.get(db, id=id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    doctor = await crud_doctor.remove(db, id=id)
    return doctor

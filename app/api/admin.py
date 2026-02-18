from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from app.api import deps
from app.crud.user import user as crud_user
from app.models.user import UserRole
from app.crud.doctor import doctor as crud_doctor
from app.crud.nurse import nurse as crud_nurse
from app.crud.patient import patient as crud_patient
from app.crud.medicine import medicine as crud_medicine
from app.crud.lab_test import lab_test as crud_lab_test
from app.crud.floor import floor as crud_floor
from app.crud.availability import availability as crud_availability
from app.schemas.doctor import DoctorCreate, DoctorResponse, DoctorRegister
from app.schemas.nurse import NurseCreate, NurseResponse, NurseRegister
from app.schemas.patient import PatientCreate, Patient
from app.schemas.medicine import MedicineCreate, Medicine
from app.schemas.lab_test import LabTestCreate, LabTest
from app.schemas.floor import FloorCreate, Floor
from app.schemas.availability import AvailabilityCreate, Availability
from app.schemas.hospital import HospitalCreate, Hospital
from app.models.user import User
from app.schemas.user import LabAssistantCreate, User as UserSchema
from app.crud.hospital import hospital as crud_hospital

router = APIRouter()

@router.get("/staff/search")
async def search_staff(
    q: str = Query(..., min_length=1),
    role_filter: str = Query(None, pattern="^(doctor|nurse)$"),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Unified search for doctors and nurses by name or email.
    Filters by current user's hospital.
    Optional role_filter: 'doctor' or 'nurse' to filter by role.
    """
    from app.models.doctor import Doctor
    from app.models.nurse import Nurse
    
    search_term = f"%{q}%"
    results = {"doctors": [], "nurses": []}
    
    # Only search within user's hospital
    if not current_user.hospital_id:
        # Super admin without hospital can't search staff
        return results
    
    # Search doctors if no filter or filter is 'doctor'
    if not role_filter or role_filter == "doctor":
        # Use Doctor.user relationship to avoid ambiguous FK error
        doctor_query = select(Doctor).options(selectinload(Doctor.user)).join(Doctor.user).filter(
            Doctor.hospital_id == current_user.hospital_id,
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        ).limit(20)
        doctor_results = await db.execute(doctor_query)
        results["doctors"] = doctor_results.scalars().all()
    
    # Search nurses if no filter or filter is 'nurse'
    if not role_filter or role_filter == "nurse":
        # Use Nurse.user relationship to avoid ambiguous FK error
        nurse_query = select(Nurse).options(selectinload(Nurse.user)).join(Nurse.user).filter(
            Nurse.hospital_id == current_user.hospital_id,
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        ).limit(20)
        nurse_results = await db.execute(nurse_query)
        results["nurses"] = nurse_results.scalars().all()
    
    return results

@router.post("/hospitals/create", response_model=Hospital)
async def create_hospital(
    *,
    db: AsyncSession = Depends(deps.get_db),
    hospital_in: HospitalCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create a new hospital and assign the current super admin as its admin.
    """
    # 1. Create Hospital
    hospital = await crud_hospital.create(db, obj_in=hospital_in)
    
    # 2. Update Super Admin's hospital_id
    current_user.hospital_id = hospital.id
    db.add(current_user)
    await db.commit()
    
    return hospital

@router.post("/doctors/create", response_model=DoctorResponse)
async def create_doctor(
    *,
    db: AsyncSession = Depends(deps.get_db),
    doctor_in: DoctorCreate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    # Logic to create doctor (and potentially user if not exists? Schema says user_id is required)
    # The schema DoctorCreate requires user_id. 
    # In a real app, admin might creating user AND doctor profile together.
    # For now, assuming user exists or separate flow.
    doctor_in.created_by = current_user.id
    
    # Get the user to promote their role
    user = await crud_user.get(db, id=doctor_in.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Only allow creating doctor profile for BASE users
    if user.role != UserRole.BASE.value:
        raise HTTPException(status_code=400, detail="User must be in BASE role to be assigned as doctor")
    
    # Check if user is already a doctor
    from app.models.doctor import Doctor
    existing_doctor_user = await db.execute(select(Doctor).filter(Doctor.user_id == doctor_in.user_id))
    if existing_doctor_user.scalars().first():
        raise HTTPException(status_code=400, detail="User is already assigned a doctor profile")

    if not doctor_in.hospital_id:
        doctor_in.hospital_id = current_user.hospital_id
    
    if not doctor_in.hospital_id:
         raise HTTPException(status_code=422, detail="Hospital ID required when creating as Super Admin without an associated hospital.")
    
    # Check for existing license number
    from app.models.doctor import Doctor
    existing_doctor = await db.execute(select(Doctor).filter(Doctor.license_number == doctor_in.license_number))
    if existing_doctor.scalars().first():
        raise HTTPException(status_code=400, detail="Doctor with this license number already exists")
    
    # Promote user role to DOCTOR and assign hospital
    user.role = UserRole.DOCTOR.value
    user.hospital_id = doctor_in.hospital_id
    db.add(user)
    await db.commit()
        
    doctor = await crud_doctor.create(db, obj_in=doctor_in)
    # Refresh with eager loading to avoid MissingGreenlet error
    await db.refresh(doctor, ["user"])
    return doctor

@router.post("/doctors/register", response_model=DoctorResponse)
async def register_doctor(
    *,
    db: AsyncSession = Depends(deps.get_db),
    reg_in: DoctorRegister,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Register a doctor by searching for an existing user (Email or Compact ID).
    """
    # Lookup User
    user_query = select(User).filter(
        or_(
            User.email == reg_in.user_search_query,
            User.compact_id == reg_in.user_search_query
        )
    )
    user = (await db.execute(user_query)).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check if user is already a doctor
    from app.models.doctor import Doctor
    existing_doctor_user = await db.execute(select(Doctor).filter(Doctor.user_id == user.id))
    if existing_doctor_user.scalars().first():
        # Maybe just return the existing doctor? 
        # But register implies new role assignment.
        # Let's error out for clarity or idempotency check.
        raise HTTPException(status_code=400, detail="User is already a doctor")

    # Promote role
    user.role = UserRole.DOCTOR.value
    db.add(user)
    
    # Create Doctor Profile
    hospital_id = reg_in.hospital_id or current_user.hospital_id
    if not hospital_id:
         raise HTTPException(status_code=422, detail="Hospital ID required.")

    doctor_in = DoctorCreate(
        user_id=user.id,
        hospital_id=hospital_id,
        specialization=reg_in.specialization,
        license_number=reg_in.license_number,
        experience_years=reg_in.experience_years,
        tags=reg_in.tags,
        created_by=current_user.id
    )
    doctor = await crud_doctor.create(db, obj_in=doctor_in)
    # Refresh with eager loading to avoid MissingGreenlet error
    await db.refresh(doctor, ["user"])
    return doctor

@router.post("/nurses/create", response_model=NurseResponse)
async def create_nurse(
    *,
    db: AsyncSession = Depends(deps.get_db),
    nurse_in: NurseCreate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    nurse_in.created_by = current_user.id
    
    # Get the user to promote their role
    user = await crud_user.get(db, id=nurse_in.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Only allow creating nurse profile for BASE users
    if user.role != UserRole.BASE.value:
        raise HTTPException(status_code=400, detail="User must be in BASE role to be assigned as nurse")
    
    # Check if user is already a nurse
    from app.models.nurse import Nurse
    existing_nurse_user = await db.execute(select(Nurse).filter(Nurse.user_id == nurse_in.user_id))
    if existing_nurse_user.scalars().first():
        raise HTTPException(status_code=400, detail="User is already assigned a nurse profile")

    if not nurse_in.hospital_id:
        nurse_in.hospital_id = current_user.hospital_id
    
    if not nurse_in.hospital_id:
         raise HTTPException(status_code=422, detail="Hospital ID required.")
    
    # Promote user role to NURSE and assign hospital
    user.role = UserRole.NURSE.value
    user.hospital_id = nurse_in.hospital_id
    db.add(user)
    await db.commit()
        
    nurse = await crud_nurse.create(db, obj_in=nurse_in)
    # Refresh with eager loading to avoid MissingGreenlet error
    await db.refresh(nurse, ["user"])
    return nurse

@router.post("/nurses/register", response_model=NurseResponse)
async def register_nurse(
    *,
    db: AsyncSession = Depends(deps.get_db),
    reg_in: NurseRegister,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Register a nurse by searching for an existing user (Email or Compact ID).
    """
    user_query = select(User).filter(
        or_(
            User.email == reg_in.user_search_query,
            User.compact_id == reg_in.user_search_query
        )
    )
    user = (await db.execute(user_query)).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.role = UserRole.NURSE.value
    db.add(user)
    
    hospital_id = reg_in.hospital_id or current_user.hospital_id
    if not hospital_id:
         raise HTTPException(status_code=422, detail="Hospital ID required.")

    nurse_in = NurseCreate(
        user_id=user.id,
        hospital_id=hospital_id,
        shift_type=reg_in.shift_type,
        created_by=current_user.id
    )
    nurse = await crud_nurse.create(db, obj_in=nurse_in)
    # Refresh with eager loading to avoid MissingGreenlet error
    await db.refresh(nurse, ["user"])
    return nurse

@router.post("/patients/create", response_model=Patient)
async def create_patient(
    *,
    db: AsyncSession = Depends(deps.get_db),
    patient_in: PatientCreate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Create a new patient.
    
    - Creates a new User account with role PATIENT
    - Creates a Patient profile linked to the User
    """
    from app.crud.user import user as crud_user
    from app.schemas.user import UserCreate
    from app.core.security import get_password_hash
    from app.models.user import UserRole
    from app.models.patient import Patient as PatientModel
    
    # Check if user with this email already exists
    existing_user = await crud_user.get_by_email(db, email=patient_in.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # 1. Create User account
    user_data = UserCreate(
        email=patient_in.email,
        full_name=patient_in.full_name,
        phone_number=patient_in.phone,
        password=get_password_hash(patient_in.password or "Patient@123"),
        role=UserRole.PATIENT,
        hospital_id=current_user.hospital_id,
        is_active=True,
        is_verified=True
    )
    created_user = await crud_user.create(db, obj_in=user_data)
    
    # 2. Create Patient profile
    patient_data = patient_in.model_dump(exclude={"email", "password"})
    patient_data["user_id"] = created_user.id
    patient_data["hospital_id"] = current_user.hospital_id
    
    patient = PatientModel(**patient_data)
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    
    return patient

@router.post("/medicines/create", response_model=Medicine)
async def create_medicine(
    *,
    db: AsyncSession = Depends(deps.get_db),
    medicine_in: MedicineCreate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    medicine_in.created_by = current_user.id
    medicine = await crud_medicine.create(db, obj_in=medicine_in)
    return medicine

@router.post("/lab-tests/create", response_model=LabTest)
async def create_lab_test(
    *,
    db: AsyncSession = Depends(deps.get_db),
    lab_test_in: LabTestCreate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    lab_test_in.created_by = current_user.id
    lab_test = await crud_lab_test.create(db, obj_in=lab_test_in)
    return lab_test

@router.post("/floors/create", response_model=Floor)
async def create_floor(
    *,
    db: AsyncSession = Depends(deps.get_db),
    floor_in: FloorCreate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    floor = await crud_floor.create(db, obj_in=floor_in)
    return floor

@router.post("/availability/create", response_model=Availability)
async def create_availability(
    *,
    db: AsyncSession = Depends(deps.get_db),
    availability_in: AvailabilityCreate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    availability = await crud_availability.create(db, obj_in=availability_in)
    return availability

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    # Mock stats or implement count queries
    return {
        "total_doctors": 0,
        "total_nurses": 0,
        "total_patients": 0,
        "total_medicines": 0,
        "low_stock_medicines": 0,
        "total_lab_tests": 0
    }
@router.put("/users/{user_id}/role", response_model=Any)
async def update_user_role(
    user_id: str,
    role: UserRole,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Update a user's role.
    """
    user = await crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Prevent modifying self role if not super admin? 
    # For simplicity, allow admin to manage users.
    
    # Check if user belongs to same hospital
    if user.hospital_id != current_user.hospital_id and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to modify this user")

    user.role = role.value
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "Role updated successfully", "user": user}

@router.post("/lab-assistants/create", response_model=UserSchema)
async def create_lab_assistant(
    *,
    db: AsyncSession = Depends(deps.get_db),
    lab_assistant_in: LabAssistantCreate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Promote a BASE user to LAB_ASSISTANT and assign to current hospital.
    """
    user = await crud_user.get(db, id=lab_assistant_in.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.role != UserRole.BASE.value:
         raise HTTPException(status_code=400, detail="User must be in BASE role to be assigned as lab assistant")
         
    # Check if user is already assigned to a hospital (if not forcing reassignment)
    if user.hospital_id and user.hospital_id != current_user.hospital_id:
         raise HTTPException(status_code=400, detail="User is already assigned to another hospital")

    user.role = UserRole.LAB_ASSISTANT.value
    user.hospital_id = current_user.hospital_id
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/lab-assistants/{user_id}", response_model=UserSchema)
async def remove_lab_assistant(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_id: str,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Remove LAB_ASSISTANT role and hospital assignment.
    """
    user = await crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.role != UserRole.LAB_ASSISTANT.value:
        raise HTTPException(status_code=400, detail="User is not a lab assistant")
        
    if user.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Not authorized to remove this staff member")

    user.role = UserRole.BASE.value
    user.hospital_id = None
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


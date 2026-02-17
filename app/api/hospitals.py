from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.crud.hospital import hospital as crud_hospital
from app.schemas.hospital import Hospital, HospitalCreate
from app.models.user import User
from app.schemas.doctor import DoctorResponse

router = APIRouter()

@router.post("/register", response_model=Hospital)
async def register_hospital(
    *,
    db: AsyncSession = Depends(deps.get_db),
    hospital_in: HospitalCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Register a new hospital.
    
    - Creates hospital record
    - Assigns hospital_id to current user
    - Upgrades user to HOSPITAL_ADMIN role
    """
    hospital = await crud_hospital.create(db, obj_in=hospital_in)
    
    # Update user with hospital_id and role
    from app.crud.user import user as crud_user
    from app.schemas.user import UserUpdate
    from app.models.user import UserRole
    
    user_update = UserUpdate(
        hospital_id=hospital.id,
        role=UserRole.HOSPITAL_ADMIN
    )
    await crud_user.update(db, db_obj=current_user, obj_in=user_update)
    
    return hospital

@router.get("/search", response_model=list[Hospital])
async def search_hospitals(
    q: str,
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Search hospitals by name.
    """
    hospitals = await crud_hospital.search(db, query=q, skip=skip, limit=limit)
    return hospitals

@router.get("/{id}", response_model=Hospital)
async def read_hospital(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get hospital details by ID.
    
    - Returns hospital information
    - Includes  registration details
    """
    hospital = await crud_hospital.get(db, id=id)
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return hospital

@router.get("/{id}/doctors/search", response_model=List[DoctorResponse])
async def search_hospital_doctors(
    id: str,
    q: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Search doctors in this hospital.
    """
    from app.crud.doctor import doctor as crud_doctor
    from app.schemas.doctor import DoctorResponse
    
    # Verify hospital exists
    hospital = await crud_hospital.get(db, id=id)
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
        
    doctors = await crud_doctor.search(db, query=q, hospital_id=id)
    return doctors

@router.get("/{id}/search", response_model=List[DoctorResponse])
async def search_hospital_stuff(
    id: str,
    q: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Search within hospital (alias for searching doctors for now).
    """
    # Reuse same logic
    return await search_hospital_doctors(id=id, q=q, db=db, current_user=current_user)

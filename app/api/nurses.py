from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.api import deps
from app.crud.nurse import nurse as crud_nurse
from app.schemas.nurse import NurseResponse, NurseUpdate
from app.schemas.user import User as UserSchema
from app.models.user import User
from app.models.nurse import Nurse

router = APIRouter()

@router.get("/search-potential", response_model=List[UserSchema])
async def search_potential_nurses(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Search for potential nurses to add.
    
    - **Admin only**
    - Searches users with NURSE role
    """
    from app.models.user import UserRole
    search_term = f"%{q}%"
    
    query = select(User).filter(
        or_(
            User.full_name.ilike(search_term),
            User.email.ilike(search_term)
        )
    ).filter(User.role == UserRole.NURSE.value).limit(20)
    
    users = (await db.execute(query)).scalars().all()
    return users

@router.get("/search", response_model=List[NurseResponse])
async def search_nurses(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Search nurses in your hospital.
    
    - Search by name  
    - Returns nurses from your hospital only
    """
    nurses = await crud_nurse.search(db, query=q, hospital_id=current_user.hospital_id)
    return nurses

@router.get("/", response_model=List[NurseResponse])
async def read_nurses(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get list of nurses.
    
    - **Hospital filtered**: Only from your hospital
    - **Pagination**: Use skip/limit
    """
    nurses = await crud_nurse.get_multi(db, skip=skip, limit=limit)
    return nurses

@router.put("/{id}", response_model=NurseResponse)
async def update_nurse(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    nurse_in: NurseUpdate,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Update nurse information.
    
    - **Admin only**
    - Modify shift, floor assignment, etc.
    """
    nurse = await crud_nurse.get(db, id=id)
    if not nurse:
        raise HTTPException(status_code=404, detail="Nurse not found")
    nurse = await crud_nurse.update(db, db_obj=nurse, obj_in=nurse_in)
    return nurse

@router.delete("/{id}", response_model=NurseResponse)
async def delete_nurse(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: str,
    current_user: User = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Remove nurse from hospital.
    
    - **Admin only**
    - Removes nurse record
    """
    nurse = await crud_nurse.get(db, id=id)
    if not nurse:
        raise HTTPException(status_code=404, detail="Nurse not found")
    nurse = await crud_nurse.remove(db, id=id)
    return nurse

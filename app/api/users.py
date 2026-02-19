from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_password_hash
from app.api import deps
from app.crud.user import user as crud_user
from app.schemas.user import User, UserUpdate, UserProfileUpdate
from app.models.user import User as UserModel, UserRole
import os
import httpx

router = APIRouter()

@router.get("/me", response_model=User)
async def read_user_me(
    current_user: UserModel = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get current user information.
    
    - Returns your user profile
    - Includes hospital association
    """
    return current_user

@router.put("/me", response_model=User)
async def update_user_me(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: UserProfileUpdate,
    current_user: UserModel = Depends(deps.get_current_active_user),
) -> Any:
    """
    Update own user profile.
    
    - Allows updating name, email, phone, and password
    """
    if user_in.email and user_in.email != current_user.email:
        # Check if email is already taken
        user = await crud_user.get_by_email(db, email=user_in.email)
        if user:
            raise HTTPException(
                status_code=400,
                detail="The user with this email already exists in the system",
            )
            
    user_data = user_in.model_dump(exclude_unset=True)
    if "password" in user_data and user_data["password"]:
        hashed_password = get_password_hash(user_data["password"])
        del user_data["password"]
        user_data["hashed_password"] = hashed_password

    # CRUDBase update method handles dict or schema
    updated_user = await crud_user.update(db, db_obj=current_user, obj_in=user_data)
    
    # Sync with Patient table if applicable
    if updated_user.role == UserRole.PATIENT.value:
        from app.crud.patient import patient as crud_patient
        patient_record = await crud_patient.get_by_user_id(db, user_id=updated_user.id)
        if patient_record:
            # We need to update patient record
            # Ideally use a schema, but for now direct update via dict/sql helpful
            # Construct update dict for Patient
            patient_update_data = {}
            if "full_name" in user_data:
                patient_update_data["full_name"] = user_data["full_name"]
            if "phone_number" in user_data: # User model has phone_number, Patient has phone
                patient_update_data["phone"] = user_data["phone_number"]
            
            if patient_update_data:
                 await crud_patient.update(db, db_obj=patient_record, obj_in=patient_update_data)

    return updated_user

@router.get("/", response_model=List[User])
async def read_users(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: UserModel = Depends(deps.get_current_hospital_admin),
) -> Any:
    """
    Retrieve users.
    
    - **Admin only**: Requires hospital_admin role
    - **Hospital filtered**: Only shows users from your hospital
    - **Pagination**: Use skip/limit for pagination
    """
    users = await crud_user.get_multi(db, skip=skip, limit=limit)
    return users

@router.post("/upload-image")
async def upload_user_image(
    file: UploadFile = File(...),
    current_user: UserModel = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Upload user profile image.
    
    - Uploads to Supabase via app.utils.file
    - Updates user profile with image URL
    """
    from app.utils.file import upload_file
    
    image_url = await upload_file(file)
    
    # Update user with image URL
    user_update = UserUpdate(image=image_url)
    updated_user = await crud_user.update(db, db_obj=current_user, obj_in=user_update)
    
    return {"image_url": image_url}

@router.get("/search/nurses", response_model=List[User])
async def search_nurses(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(deps.get_db),
    current_user: UserModel = Depends(deps.get_current_active_user), # Any staff can search?
) -> Any:
    """
    Search for nurses by name or email.
    Used by doctors to assign nurses.
    """
    from sqlalchemy import select, or_
    
    search_term = f"%{q}%"
    
    query = select(UserModel).filter(
        UserModel.hospital_id == current_user.hospital_id,
        UserModel.role == UserRole.NURSE.value,
        or_(
            UserModel.full_name.ilike(search_term),
            UserModel.email.ilike(search_term)
        )
    ).limit(20)
    
    result = await db.execute(query)
    return result.scalars().all()

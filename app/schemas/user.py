from typing import Optional
from pydantic import BaseModel, EmailStr
from app.models.user import UserRole

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    role: UserRole = UserRole.HOSPITAL_ADMIN
    is_active: Optional[bool] = True
    is_verified: Optional[bool] = False
    compact_id: Optional[str] = None
    image: Optional[str] = None
    hospital_id: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    image: Optional[str] = None
    hospital_id: Optional[str] = None

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None

class UserInDBBase(UserBase):
    id: str

    class Config:
        from_attributes = True

class User(UserInDBBase):
    pass

class UserInDB(UserInDBBase):
    hashed_password: str

class LabAssistantCreate(BaseModel):
    user_id: str

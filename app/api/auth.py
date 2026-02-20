from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.core import security
from app.core.oauth import oauth
from app.core.config import settings
from app.crud.user import user as crud_user
from app.crud.hospital import hospital as crud_hospital
from app.schemas.auth import Token
from app.schemas.user import User, UserCreate
from app.schemas.hospital import HospitalCreate
from app.models.user import UserRole

router = APIRouter()

@router.post("/login/access-token", response_model=Token)
async def login_access_token(
    db: AsyncSession = Depends(deps.get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login.
    
    - Get an access token for future requests
    - Use email as username
    -Returns JWT bearer token valid for configured duration
    """
    user = await crud_user.authenticate(
        db, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }

@router.post("/register", response_model=User)
async def register_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: UserCreate,
    hospital_in: HospitalCreate = None
) -> Any:
    """
    Register a new user.
    
    - Create a new user account
    - Optionally create and link a hospital
    - If hospital is provided, user becomes hospital admin
    - Returns the created user object
    """
    user = await crud_user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system",
        )
    
    # Optional logic: create hospital if provided, but typically register is just for user or with existing hospital
    # For now simplicity: just create user. If hospital_id is in user_in, it links.
    if hospital_in:
        # Create Hospital
        hospital = await crud_hospital.create(db, obj_in=hospital_in)
        
        # Link User to Hospital and make them Admin
        user_in.hospital_id = hospital.id
        user_in.role = UserRole.HOSPITAL_ADMIN
        
        # Determine if we should set admin_email on hospital? 
        # The schema has it, might be good to sync back.
        # But crud_hospital.create already ran. We can update it or just trust the input.
    else:
        # Standard user registration -> Force BASE role
        user_in.role = UserRole.BASE
        user_in.hospital_id = None
        
    user = await crud_user.create(db, obj_in=user_in)
    return user

@router.get("/login/google")
async def login_google(request: Request):
    """
    Initiate Google OAuth login flow.
    
    - Redirects to Google login page
    - User authenticates with Google
    - Returns to callback URL after authentication
    """
    return await oauth.google.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)


@router.get("/google/callback")
async def auth_google_callback(
    request: Request,
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Google OAuth callback handler.
    
    - Receives authorization code from Google
    - Exchanges code for user information
    - Creates user if doesn't exist (auto-registration)
    - Generates JWT token and redirects to frontend with token
    """
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth Error: {str(e)}")

    user_info = token.get('userinfo')
    if not user_info:
        # Sometimes userinfo is in 'id_token' claim decoded, let's try fetch userinfo endpoint if needed
        # But with openid scope, authorize_access_token usually parses id_token
        # Let's check token['userinfo'] first. If not present, we might need to parse id_token manually 
        # but Authlib usually handles this if 'openid' scope is present.
        # Fallback:
        user_info = await oauth.google.userinfo(token=token)

    if not user_info:
        raise HTTPException(status_code=400, detail="Could not retrieve user info")

    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not found in token")
        
    user = await crud_user.get_by_email(db, email=email)
    if not user:
        # Auto-create user
        user_in = UserCreate(
            email=email,
            full_name=user_info.get("name"),
            password=security.get_password_hash("google_oauth_placeholder"), # Dummy password
            is_active=True,
            is_verified=True,
            role="base", # Default role as requested
            image=user_info.get("picture")
        )
        user = await crud_user.create(db, obj_in=user_in)
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    
    # Redirect to frontend with token
    # Using http://localhost:8080/oauth-success?token=<JWT> as requested
    frontend_url = f"http://localhost:8080/oauth-success?token={access_token}"
    return RedirectResponse(url=frontend_url)

from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests

class GoogleAuthRequest(BaseModel):
    id_token: str

@router.post("/google-mobile")
async def auth_google_mobile(
    data: GoogleAuthRequest,
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Mobile Google Auth endpoint.
    
    Accepts an ID token directly from the mobile app's Google login SDK,
    verifies it with Google, issues an app JWT, and creates user if missing.
    """
    try:
        # Verify the token against Google's public keys
        # We don't strictly pass the client ID here to allow multiple clients (iOS/Android/Web),
        # but we could enforce it for stricter security.
        idinfo = id_token.verify_oauth2_token(
            data.id_token, requests.Request(), clock_skew_in_seconds=10
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid Google token: {str(e)}")

    email = idinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not found in Google token")

    # Check if user exists
    user = await crud_user.get_by_email(db, email=email)
    
    if not user:
        # Auto-create user
        user_in = UserCreate(
            email=email,
            full_name=idinfo.get("name", ""),
            password=security.get_password_hash("google_mobile_oauth_placeholder"),
            is_active=True,
            is_verified=True,
            role="patient", # Default mobile signups to patient role
            image=idinfo.get("picture", "")
        )
        user = await crud_user.create(db, obj_in=user_in)
        
        # Also create a patient record for new patients
        from app.crud.patient import patient as crud_patient
        from app.schemas.patient import PatientCreate
        patient_in = PatientCreate(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
        )
        await crud_patient.create(db, obj_in=patient_in)
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "image": user.image
        }
    }
async def read_users_me(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get current authenticated user information.
    
    - Returns the logged-in user's profile
    - Requires valid JWT token
    - Includes role, hospital affiliation, and other user details
    """
    return current_user

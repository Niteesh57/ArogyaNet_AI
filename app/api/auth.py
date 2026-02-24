from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from app.utils.wake_up import wake_up_huggingface
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(deps.get_db), 
    form_data: OAuth2PasswordRequestForm = Depends()
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
    
    # Wake up HuggingFace space in background
    background_tasks.add_task(wake_up_huggingface)
    
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
    background_tasks: BackgroundTasks,
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
            password=security.get_password_hash("123456789N"), # Dummy password
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
    frontend_url = f"{settings.FRONTEND_URL}/oauth-success?token={access_token}"
    
    # Wake up HuggingFace space in background
    background_tasks.add_task(wake_up_huggingface)
    
    return RedirectResponse(url=frontend_url)

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

@router.post("/google", response_model=Token)
async def google_auth_mobile(
    data: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(deps.get_db)
) -> Any:
    """
    Google OAuth token verification for Mobile App.
    
    - Receives Google ID token from frontend
    - Verifies token directly with Google
    - Creates user if doesn't exist
    - Returns JWT access token
    """
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
        
    try:
        # User explicitly provided the WEB client id for Android/iOS GoogleSignin
        CLIENT_ID = "994195201263-nl156b5t0elh72k9v4lho8mfrg7sv2lj.apps.googleusercontent.com"
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            CLIENT_ID
        )

        email = idinfo.get("email")
        name = idinfo.get("name")
        picture = idinfo.get("picture")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email not found in token")
            
        user = await crud_user.get_by_email(db, email=email)
        
        if not user:
            # Auto-create user
            user_in = UserCreate(
                email=email,
                full_name=name,
                password=security.get_password_hash("123456789N"), # Dummy password
                is_active=True,
                is_verified=True,
                role="base", # Default role
                image=picture
            )
            user = await crud_user.create(db, obj_in=user_in)
        
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
            
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        # Wake up HuggingFace space in background
        background_tasks.add_task(wake_up_huggingface)
        
        return {
            "access_token": security.create_access_token(
                user.id, expires_delta=access_token_expires
            ),
            "token_type": "bearer",
        }

    except ValueError as e:
        print(f"Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid Google token")

@router.get("/me", response_model=User)
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

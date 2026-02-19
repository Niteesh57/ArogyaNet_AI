from contextlib import asynccontextmanager
import subprocess
import sys
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.api import api_router
from app.core.config import settings
from app.core.database import engine, Base
from app.core.security import get_password_hash
from app.models import specialization, user, document
from sqlalchemy import select
from app.core.database import SessionLocal

from app.agent.LLM.llm import get_vqa_chain, get_medasr_chain, get_hear_model, get_path_foundation

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger = logging.getLogger("uvicorn.error")
    logger.info("Starting LiveKit Agent Worker...")
    agent_process = None
    try:
        # Run the agent as a subprocess
        agent_process = subprocess.Popen([sys.executable, "-m", "app.agent.callAgent", "start"])
    except Exception as e:
        logger.error(f"Failed to start agent worker: {e}")

    # Startup
    # Load AI Models (MedASR)
    # Load AI Models
    # try:
       # get_medasr_chain()
    # except Exception as e:
    #     print(f"Warning: Failed to load MedASR model on startup: {e}")

    try:
        get_vqa_chain()
        # get_hear_model()
        # get_path_foundation()
    except Exception as e:
        print(f"Warning: Failed to load MedVQA model on startup: {e}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with SessionLocal() as db:
        # Seed Specializations
        specs = ["General Medicine", "Cardiology", "Orthopedics", "Pediatrics", "Neurology", "Oncology"]
        for spec_name in specs:
            result = await db.execute(select(specialization.Specialization).filter(specialization.Specialization.name == spec_name))
            if not result.scalars().first():
                db.add(specialization.Specialization(name=spec_name))
        
        # Seed Superuser
        result = await db.execute(select(user.User).filter(user.User.email == settings.FIRST_SUPERUSER))
        if not result.scalars().first():
            superuser = user.User(
                email=settings.FIRST_SUPERUSER,
                hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
                full_name="Super Admin",
                role=user.UserRole.SUPER_ADMIN.value,
                is_active=True,
                is_verified=True
            )
            db.add(superuser)
        
        await db.commit()
    
    yield
    # Shutdown
    if agent_process:
        logger.info("Stopping LiveKit Agent Worker...")
        agent_process.terminate()
        try:
            agent_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            agent_process.kill()
    
    # await engine.dispose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

from starlette.middleware.sessions import SessionMiddleware

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to Life Health CRM API"}

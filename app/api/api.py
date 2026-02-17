from fastapi import APIRouter
from app.api import auth, admin, hospitals, users, doctors, nurses, patients, inventory, lab_tests, floors, availability, search, appointments, lab_reports, agent

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(hospitals.router, prefix="/hospitals", tags=["hospitals"])
api_router.include_router(hospitals.router, prefix="/hospital", tags=["hospitals"]) # Alias for singular
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(doctors.router, prefix="/doctors", tags=["doctors"])
api_router.include_router(nurses.router, prefix="/nurses", tags=["nurses"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
api_router.include_router(appointments.router, prefix="/appointments", tags=["appointments"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(lab_tests.router, prefix="/lab-tests", tags=["lab-tests"])
api_router.include_router(lab_reports.router, prefix="/lab-reports", tags=["lab-reports"])
api_router.include_router(floors.router, prefix="/floors", tags=["floors"])
api_router.include_router(availability.router, prefix="/availability", tags=["availability"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(agent.router, prefix="/agent", tags=["AI Agent"])

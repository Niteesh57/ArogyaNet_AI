from typing import List, Optional, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientUpdate

class CRUDPatient(CRUDBase[Patient, PatientCreate, PatientUpdate]):
    async def get(self, db: AsyncSession, id: Any) -> Optional[Patient]:
        # Patient relationships: hospital, assigned_doctor (which has user), etc.
        # Check models/patient.py if needed, but safe bet is selectinload(Patient.hospital)
        # and maybe assigned_doctor.
        query = select(Patient).options(
            selectinload(Patient.hospital),
            selectinload(Patient.assigned_doctor).selectinload(Doctor.user)
        ).filter(Patient.id == id)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[Patient]:
        query = select(Patient).options(
            selectinload(Patient.hospital),
            selectinload(Patient.assigned_doctor).selectinload(Doctor.user)
        ).offset(skip).limit(limit)
        return result.scalars().all()

    async def get_by_user_id(self, db: AsyncSession, *, user_id: str) -> Optional[Patient]:
        query = select(Patient).filter(Patient.user_id == user_id)
        result = await db.execute(query)
        return result.scalars().first()

patient = CRUDPatient(Patient)

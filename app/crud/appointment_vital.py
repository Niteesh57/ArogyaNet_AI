from typing import Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.appointment_vital import AppointmentVital
from app.schemas.appointment_vital import AppointmentVitalCreate, AppointmentVitalUpdate

class CRUDAppointmentVital(CRUDBase[AppointmentVital, AppointmentVitalCreate, AppointmentVitalUpdate]):
    async def get_by_appointment(
        self, db: AsyncSession, *, appointment_id: str
    ) -> List[AppointmentVital]:
        from sqlalchemy import select
        from app.models.user import User
        from sqlalchemy.orm import selectinload
        
        # Since AppointmentVital.nurse is a relationship to User, we need to ensure User is imported
        # and we load it.
        # Check if we need to load User from app.models.user
        
        query = select(AppointmentVital).options(
            selectinload(AppointmentVital.nurse)
        ).filter(
            AppointmentVital.appointment_id == appointment_id
        ).order_by(AppointmentVital.created_at.desc())
        
        result = await db.execute(query)
        return result.scalars().all()

appointment_vital = CRUDAppointmentVital(AppointmentVital)

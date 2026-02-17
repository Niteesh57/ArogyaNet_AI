from typing import Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.appointment import Appointment
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate

class CRUDAppointment(CRUDBase[Appointment, AppointmentCreate, AppointmentUpdate]):
    async def get_by_doctor_date(
        self, db: AsyncSession, *, doctor_id: str, date: Any
    ) -> list[Appointment]:
        from sqlalchemy import select
        # Cast date to ensure comparison works
        query = select(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.date == date
        )
        result = await db.execute(query)
        return result.scalars().all()

appointment = CRUDAppointment(Appointment)

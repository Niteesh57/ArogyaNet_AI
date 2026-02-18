from typing import Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.appointment import Appointment
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate

class CRUDAppointment(CRUDBase[Appointment, AppointmentCreate, AppointmentUpdate]):
    async def get_by_patient(
        self, db: AsyncSession, *, patient_id: str
    ) -> list[Appointment]:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload, joinedload
        from app.models.doctor import Doctor
        
        query = select(Appointment).options(
            selectinload(Appointment.doctor).selectinload(Doctor.user),
            selectinload(Appointment.doctor).selectinload(Doctor.hospital),
            selectinload(Appointment.nurse)
        ).filter(
            Appointment.patient_id == patient_id
        ).order_by(Appointment.date.desc(), Appointment.slot.asc())
        
        result = await db.execute(query)
        return result.scalars().all()

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

    async def get_by_patient_and_doctor(
        self, db: AsyncSession, *, patient_id: str, doctor_id: str
    ) -> list[Appointment]:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.doctor import Doctor
        
        query = select(Appointment).options(
            selectinload(Appointment.doctor).selectinload(Doctor.user),
            selectinload(Appointment.doctor).selectinload(Doctor.hospital),
            selectinload(Appointment.nurse)
        ).filter(
            Appointment.patient_id == patient_id,
            Appointment.doctor_id == doctor_id
        ).order_by(Appointment.date.desc(), Appointment.slot.desc())
        
        result = await db.execute(query)
        return result.scalars().all()

appointment = CRUDAppointment(Appointment)

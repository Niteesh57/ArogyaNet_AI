from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from app.crud.base import CRUDBase
from app.models.doctor_patient_chat import DoctorPatientChat
from app.schemas.doctor_patient_chat import ChatMessageCreate

class CRUDDoctorPatientChat(CRUDBase[DoctorPatientChat, ChatMessageCreate, ChatMessageCreate]):
    async def get_chat_history(
        self, db: AsyncSession, *, user1_id: str, user2_id: str, skip: int = 0, limit: int = 100
    ) -> List[DoctorPatientChat]:
        query = (
            select(DoctorPatientChat)
            .where(
                or_(
                    and_(DoctorPatientChat.sender_id == user1_id, DoctorPatientChat.receiver_id == user2_id),
                    and_(DoctorPatientChat.sender_id == user2_id, DoctorPatientChat.receiver_id == user1_id),
                )
            )
            .order_by(DoctorPatientChat.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def get_last_message(
        self, db: AsyncSession, *, user1_id: str, user2_id: str
    ) -> DoctorPatientChat | None:
        query = (
            select(DoctorPatientChat)
            .where(
                or_(
                    and_(DoctorPatientChat.sender_id == user1_id, DoctorPatientChat.receiver_id == user2_id),
                    and_(DoctorPatientChat.sender_id == user2_id, DoctorPatientChat.receiver_id == user1_id),
                )
            )
            .order_by(DoctorPatientChat.created_at.desc())
            .limit(1)
        )
        result = await db.execute(query)
        return result.scalars().first()

chat = CRUDDoctorPatientChat(DoctorPatientChat)

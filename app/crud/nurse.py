from typing import List, Optional, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.nurse import Nurse
from app.schemas.nurse import NurseCreate, NurseUpdate

class CRUDNurse(CRUDBase[Nurse, NurseCreate, NurseUpdate]):
    async def get(self, db: AsyncSession, id: Any) -> Optional[Nurse]:
        query = select(Nurse).options(selectinload(Nurse.user), selectinload(Nurse.hospital)).filter(Nurse.id == id)
        result = await db.execute(query)
        return result.scalars().first()

    async def search(
        self, db: AsyncSession, *, query: str, hospital_id: str
    ) -> List[Nurse]:
        from app.models.user import User
        from sqlalchemy import or_
        
        search_term = f"%{query}%"
        stmt = select(Nurse).join(Nurse.user).filter(
            Nurse.hospital_id == hospital_id,
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        ).options(selectinload(Nurse.user))
        
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[Nurse]:
        query = select(Nurse).options(selectinload(Nurse.user), selectinload(Nurse.hospital)).offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

nurse = CRUDNurse(Nurse)

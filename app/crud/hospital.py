from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.hospital import Hospital
from app.schemas.hospital import HospitalCreate, HospitalUpdate

class CRUDHospital(CRUDBase[Hospital, HospitalCreate, HospitalUpdate]):
    async def search(
        self, db: AsyncSession, *, query: str, skip: int = 0, limit: int = 20
    ) -> list[Hospital]:
        from sqlalchemy import select
        
        search_term = f"%{query}%"
        stmt = select(Hospital).filter(
            Hospital.name.ilike(search_term)
        ).offset(skip).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()

hospital = CRUDHospital(Hospital)

from typing import List, Optional, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.doctor import Doctor
from app.schemas.doctor import DoctorCreate, DoctorUpdate

class CRUDDoctor(CRUDBase[Doctor, DoctorCreate, DoctorUpdate]):
    async def get(self, db: AsyncSession, id: Any) -> Optional[Doctor]:
        query = select(Doctor).options(selectinload(Doctor.user), selectinload(Doctor.hospital)).filter(Doctor.id == id)
        result = await db.execute(query)
        return result.scalars().first()

    async def search(
        self, 
        db: AsyncSession, 
        *, 
        query: str, 
        hospital_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[Doctor]:
        """Search doctors by name or specialization."""
        from sqlalchemy import or_
        from app.models.user import User
        
        search_term = f"%{query}%"
        
        # Build query
        stmt = select(Doctor).options(
            selectinload(Doctor.user), 
            selectinload(Doctor.hospital)
        ).join(User, Doctor.user_id == User.id).filter(
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term),
                Doctor.specialization.ilike(search_term)
            )
        )
        
        # Filter by hospital if provided
        if hospital_id:
            stmt = stmt.filter(Doctor.hospital_id == hospital_id)
        
        stmt = stmt.offset(skip).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[Doctor]:
        query = select(Doctor).options(selectinload(Doctor.user), selectinload(Doctor.hospital)).offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

doctor = CRUDDoctor(Doctor)

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.crud.base import CRUDBase
from app.models.availability import Availability
from app.schemas.availability import AvailabilityCreate, AvailabilityUpdate

class CRUDAvailability(CRUDBase[Availability, AvailabilityCreate, AvailabilityUpdate]):
    async def get_by_staff_day(
        self, db: AsyncSession, *, staff_id: str, day_of_week: str
    ) -> Optional[Availability]:
        from sqlalchemy import select
        query = select(Availability).filter(
            Availability.staff_id == staff_id,
            Availability.day_of_week == day_of_week
        )
        result = await db.execute(query)
        return result.scalars().first()

availability = CRUDAvailability(Availability)

"""
Database initialization script
Recreates all tables with the latest schema
"""
import asyncio
from app.core.database import engine, Base
from app.models import user, hospital, doctor, nurse, patient, medicine, lab_test, floor, availability, appointment, lab_report

async def init_db():
    """Initialize database with all tables"""
    async with engine.begin() as conn:
        # Drop all tables
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database initialized successfully!")
    print("All tables created with latest schema.")

if __name__ == "__main__":
    asyncio.run(init_db())

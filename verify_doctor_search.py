import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import SessionLocal
from app.models.user import User
from app.models.doctor import Doctor

async def verify_search():
    async with SessionLocal() as db:
        print("Checking for 'bv nagi'...")
        # Check User
        stmt = select(User).filter(User.full_name.ilike("%bv nagi%"))
        result = await db.execute(stmt)
        users = result.scalars().all()
        print(f"Found {len(users)} users matching 'bv nagi':")
        for u in users:
            print(f"  - User ID: {u.id}, Name: {u.full_name}, Email: {u.email}, Role: {u.role}")
            
            # Check if doctor
            stmt_doc = select(Doctor).filter(Doctor.user_id == u.id)
            doc_result = await db.execute(stmt_doc)
            doctor = doc_result.scalars().first()
            
            if doctor:
                print(f"    -> IS DOCTOR. Doctor ID: {doctor.id}")
                print(f"       Hospital ID: {doctor.hospital_id}")
                print(f"       Target Hospital ID: 7634e58b-64bb-4053-90d6-1385b209718d")
                
                if str(doctor.hospital_id) == "7634e58b-64bb-4053-90d6-1385b209718d":
                    print("       MATCH! Should be found.")
                else:
                    print("       MISMATCH! Hospital ID differs.")
            else:
                print("    -> NOT A DOCTOR.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(verify_search())

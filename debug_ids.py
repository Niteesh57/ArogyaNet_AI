
import asyncio
from app.core.database import SessionLocal
from app.crud.patient import patient as crud_patient
from app.crud.nurse import nurse as crud_nurse
from app.crud.user import user as crud_user
from app.models.nurse import Nurse
from app.models.patient import Patient
from sqlalchemy import select

async def debug_check():
    async with SessionLocal() as db:
        patient_id = "97072414-848a-4be7-a116-baf1eabff3e7"
        nurse_id_param = "7fd94b16-e813-4d18-b605-5283acc704a6"
        
        print(f"Checking Patient: {patient_id}")
        patient = await crud_patient.get(db, id=patient_id)
        if patient:
            print(f"✅ Patient Found: {patient.id} | Name: {patient.full_name} | User ID: {patient.user_id}")
        else:
            print(f"❌ Patient Not Found: {patient_id}")
            
        print(f"\nChecking Nurse (as Nurse Profile ID): {nurse_id_param}")
        nurse = await crud_nurse.get(db, id=nurse_id_param)
        if nurse:
            print(f"✅ Nurse Profile Found: {nurse.id} | User ID: {nurse.user_id}")
        else:
            print(f"❌ Nurse Profile Not Found using ID: {nurse_id_param}")
            
            # Check if this ID is actually a User ID?
            print(f"Checking if ID {nurse_id_param} is a User ID instead...")
            user = await crud_user.get(db, id=nurse_id_param)
            if user:
                print(f"⚠️ Found User with this ID! Role: {user.role}")
                # Does this user have a nurse profile?
                stmt = select(Nurse).filter(Nurse.user_id == user.id)
                res = await db.execute(stmt)
                nurse_profile = res.scalars().first()
                if nurse_profile:
                    print(f"   -> This User has a Nurse Profile ID: {nurse_profile.id}")
                else:
                    print(f"   -> This User exists but has NO Nurse Profile.")
            else:
                print(f"❌ ID not found in User table either.")

if __name__ == "__main__":
    asyncio.run(debug_check())

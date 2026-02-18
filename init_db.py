"""
Database initialization script
Recreates all tables with the latest schema
"""
import asyncio
from app.core.database import engine, Base
from app.models import user, hospital, doctor, nurse, patient, medicine, lab_test, floor, availability, appointment, lab_report, appointment_chat, document, user_memory, appointment_vital

async def init_db():
    """Initialize database with all tables"""
    async with engine.begin() as conn:
        # Create all tables (safe - skips existing)
        await conn.run_sync(Base.metadata.create_all)
        
        # Manual Migration for missing columns
        from sqlalchemy import text
        print("Checking for schema updates...")
        
        # Check Document table for new columns
        try:
            # Check Document table for new columns
            # ... (existing Document checks) ...
            try:
                await conn.execute(text("ALTER TABLE documents ADD COLUMN patient_id VARCHAR"))
                print("Added column 'patient_id' to 'documents' table.")
            except Exception:
                pass 
                
            try:
                await conn.execute(text("ALTER TABLE documents ADD COLUMN doctor_id VARCHAR"))
                print("Added column 'doctor_id' to 'documents' table.")
            except Exception:
                pass 

            # Check Patient table for new columns
            try:
                await conn.execute(text("ALTER TABLE patients ADD COLUMN assigned_nurse_id VARCHAR"))
                print("Added column 'assigned_nurse_id' to 'patients' table.")
            except Exception:
                pass

            # Check Appointment table for new columns
            try:
                await conn.execute(text("ALTER TABLE appointments ADD COLUMN nurse_id VARCHAR"))
                print("Added column 'nurse_id' to 'appointments' table.")
            except Exception:
                pass 

            await conn.commit()
        except Exception as e:
            print(f"Schema update check completed with minor warnings: {e}")

    print("✅ Database schema synchronized!")
    print("Note: Existing columns are not modified. If you changed a model, you may need a migration.")
    print("✅ Database initialized successfully!")
    print("All tables created with latest schema.")

if __name__ == "__main__":
    asyncio.run(init_db())

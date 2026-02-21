import json
import google.generativeai as genai
from app.core.config import settings
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.appointment import Appointment

# Configure Gemini
if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

async def stream_diet_plan(appointment_id: str, patient_problem: str, doctor_remarks: str, db: AsyncSession):
    """
    Generate and stream a diet plan using Gemini API based on patient's problem and doctor's remarks.
    Returns SSE events with the generated plan.
    """
    try:
        system_prompt = f"""You are an Expert Clinical Nutritionist and Healthcare Professional working as a Diet Planner Agent.
Your task is to create a highly specific, customized, day-wise diet plan for a patient based on their diagnosed problem and their doctor's exact remarks.
You MUST strictly follow the doctor's constraints and recommendations.

Patient Problem: {patient_problem}
Doctor's Remarks: {doctor_remarks}

Requirements for the output:
1. Provide a realistic, day-wise diet plan meant to be followed strictly.
2. For each day, include specific timestamps or clear meal times (e.g., "08:00 AM - Breakfast:", "11:00 AM - Mid-Morning Snack:", "01:30 PM - Lunch:").
3. Be highly prescriptive and clear about what to eat and avoid based exactly on the constraints.
4. Organize the plan clearly with markdown formatting (e.g., Headers for Days, bold for times).
5. **IMPORTANT:** Include two separate sections at the end:
   - **Recommended Foods (Foods to Take):** A list of specific foods that will benefit the patient.
   - **Foods to Avoid:** A list of specific foods the patient must stay away from.
6. **LANGUAGE CONSTRAINT:** You MUST write the entire response in the SAME LANGUAGE as the Doctor's Remarks provided above. If the remarks are in Hindi, the plan must be in Hindi. If they are in English, the plan must be in English.
7. Add a brief, encouraging conclusion.

Example Format:
### Day 1
**08:00 AM - Breakfast:** 1 bowl of oatmeal with fresh berries (no added sugar).
...
### Day 7
...
### Recommended Foods (Foods to Take)
- ...
### Foods to Avoid
- ...

Remember, you are speaking directly to the user (patient) on behalf of the healthcare team. Keep a professional yet compassionate tone.
"""
        model_name = settings.GENERAL_MODEL or "gemini-1.5-flash"
        model = genai.GenerativeModel(model_name)
        
        response = model.generate_content(system_prompt, stream=True)
        
        full_plan = ""
        for chunk in response:
            if chunk.text:
                full_plan += chunk.text
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.text})}\n\n"
        
        # Save to database
        try:
            stmt = update(Appointment).where(Appointment.id == appointment_id).values(diet_plan=full_plan)
            await db.execute(stmt)
            await db.commit()
        except Exception as db_e:
            print(f"Error saving diet plan to DB: {db_e}")

        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

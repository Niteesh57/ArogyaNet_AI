import logging
from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    RoomInputOptions,
)
from livekit.plugins import google
from app.agent.Tools.CallTools import book_appointment, check_availability

load_dotenv()
logger = logging.getLogger("receptionist-agent")


class ReceptionistAgent(Agent):
    def __init__(self, instructions: str):
        super().__init__(
            instructions=instructions,
            tools=[book_appointment, check_availability],
        )


async def entrypoint(ctx: JobContext):
    logger.info("Starting Receptionist Agent")

    await ctx.connect()
    
    # Extract appointment_id and doctor_prompt from metadata
    appointment_id = None
    doctor_prompt = None
    if ctx.job.metadata:
        import json
        try:
            metadata = json.loads(ctx.job.metadata)
            appointment_id = metadata.get("appointment_id")
            doctor_prompt = metadata.get("doctor_prompt")
        except:
            logger.warning("Failed to parse metadata JSON")
            
    # Default context
    doctor_name = "your doctor"
    hospital_name = "LifeHealth Hospital"
    patient_name = "there"
    
    # Fetch details if appointment_id is present
    if appointment_id:
        from app.core.database import SessionLocal
        from sqlalchemy import select
        from app.models.appointment import Appointment
        from app.models.doctor import Doctor
        from app.models.user import User
        from app.models.hospital import Hospital
        from sqlalchemy.orm import selectinload

        async with SessionLocal() as db:
            # We need a custom query to get doctor name, hospital, and remarks
            query = select(Appointment).options(
                selectinload(Appointment.doctor).selectinload(Doctor.user),
                selectinload(Appointment.doctor).selectinload(Doctor.hospital),
                selectinload(Appointment.patient)
            ).filter(Appointment.id == appointment_id)
            
            result = await db.execute(query)
            appointment = result.scalars().first()
            
            if appointment:
                if appointment.doctor:
                    if appointment.doctor.user:
                        doctor_name = f"Dr. {appointment.doctor.user.full_name}"
                    if appointment.doctor.hospital:
                        hospital_name = appointment.doctor.hospital.name
                
                if appointment.patient:
                    patient_name = appointment.patient.full_name

    patient_id_context = f" (Patient ID: {appointment.patient_id})" if appointment else ""
    
    if doctor_prompt:
        agent_task_instruction = (
            f"The doctor has requested you to ask the patient the following questions: {doctor_prompt}. "
            "Ask these questions and listen to their response. After you have gathered the answers, say thanks and goodbye to finish the call. "
        )
    else:
        agent_task_instruction = (
            "Ask them if their prescribed medications are working fine and if they are facing any difficulties. "
            "If they say everything is fine, say thanks and goodbye. "
            "If they report issues, suggest booking a follow-up appointment with the doctor. "
            "Use the check_availability tool to find a slot, then book_appointment if they agree. "
            f"IMPORTANT: Pass the Patient ID {patient_id_context} to the book_appointment tool."
        )

    instructions = (
        f"You are a helpful medical assistant calling from {hospital_name} on behalf of {doctor_name}. "
        "You speak with a clear Indian accent and have a professional, empathetic female voice. "
        f"You are speaking with {patient_name}{patient_id_context}. "
        f"{agent_task_instruction}"
    )

    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            instructions=instructions,
            voice="Aoede"
        )
    )

    await session.start(
        agent=ReceptionistAgent(instructions=instructions),
        room=ctx.room
    )

    await session.generate_reply()

    # Wait for the session to finish before trying to read the history
    # The agent session will block until the room is disconnected if run properly, 
    # but in livekit-agents it might exit earlier. However, since the script ends when the room closes,
    # we can just fetch the chat context right here.
    logger.info(f"Agent session finished. Saving call script for appointment: {appointment_id}")
    if appointment_id:
        try:
            from app.core.database import SessionLocal
            from app.models.call_script import CallScript

            history = getattr(session, 'history', getattr(session, 'chat_ctx', None))
            if history is not None:
                messages_attr = getattr(history, 'messages', [])
                messages = messages_attr() if callable(messages_attr) else messages_attr
                
                if messages:
                    async with SessionLocal() as db:
                        for msg in messages:
                            role = getattr(msg, 'role', '')
                            if role not in ('user', 'assistant'):
                                continue

                            content_str = getattr(msg, 'text_content', '')
                            if not content_str:
                                content = getattr(msg, 'content', '')
                                if isinstance(content, list):
                                    text_parts = []
                                    for c in content:
                                        if hasattr(c, 'text') and c.text:
                                            text_parts.append(c.text)
                                        elif isinstance(c, str):
                                            text_parts.append(c)
                                    content_str = ' '.join(text_parts)
                                else:
                                    content_str = str(content)

                            if not content_str or not content_str.strip():
                                continue

                            db.add(CallScript(
                                appointment_id=appointment_id,
                                speaker='agent' if role == 'assistant' else 'user',
                                message=content_str.strip()
                            ))
                        await db.commit()
                        logger.info("Successfully populated call_scripts into database.")
        except Exception as e:
            logger.error(f"Failed to save call script: {e}")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="receptionist-agent",
        )
    )
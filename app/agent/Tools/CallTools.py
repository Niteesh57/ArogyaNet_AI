from livekit.agents import function_tool, RunContext
import logging

logger = logging.getLogger(__name__)

@function_tool
async def book_appointment(
    context: RunContext,
    doctor_type: str,
    preferred_time: str,
):
    """Call this tool ONLY when the user explicitly agrees to book an appointment with a doctor.
    
    Args:
        doctor_type: The specific type of doctor the user needs (e.g., cardiologist, general physician).
        preferred_time: The date and time the user wants the appointment.
    """
    logger.info(f"*** TOOL TRIGGERED: Booking {doctor_type} at {preferred_time} ***")
    
    # TODO: Insert your actual database or API booking logic here
    
    # The return value is automatically spoken back to the user by Gemini
    return f"Successfully confirmed the {doctor_type} appointment for {preferred_time}."

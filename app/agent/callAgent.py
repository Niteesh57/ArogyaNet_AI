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
from app.agent.Tools.CallTools import book_appointment

load_dotenv()
logger = logging.getLogger("receptionist-agent")


class ReceptionistAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=(
                "You are a helpful medical receptionist. "
                "Briefly greet the user and ask if they would like to book a doctor appointment. "
                "If yes, ask doctor type and preferred time. "
                "When you have both, call book_appointment."
            ),
            tools=[book_appointment],
        )


async def entrypoint(ctx: JobContext):
    logger.info("Starting Receptionist Agent")

    await ctx.connect()

    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            instructions=(
                "You are a helpful medical receptionist. "
                "Greet the caller and ask if they want to book an appointment."
            )
        )
    )

    await session.start(
        agent=ReceptionistAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            close_on_disconnect=True
        )
    )

    await session.generate_reply()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="receptionist-agent",
        )
    )
import logging
import os
from dotenv import load_dotenv
from livekit import api
from app.core.config import settings

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def trigger_call(phone_number: str):
    """
    Triggers an outbound call to the specified phone number using LiveKit SIP.
    """
    # Initialize LiveKit API
    # Note: connect() is not needed for the python SDK's LiveKitAPI class in recent versions 
    # if using environment variables (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET),
    # but we should ensure they are loaded.
    
    lkapi = api.LiveKitAPI(
        url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    
    # Create a unique room name
    room_name = f"appointment-room-{phone_number[-4:]}"
    
    try:
        # 1. Dispatch the AI Agent into the room first
        # We assume the agent is running as a worker and listening for job requests 
        # or that we are just creating a room here for the worker to join if configured that way.
        # However, typically 'create_dispatch' suggests we are explicitly asking an agent to join.
        
        logger.info(f"Starting AI Agent in room: {room_name}")
        
        # Note: In some LiveKit setups, you might rely on the agent to auto-join rooms.
        # But here we stick to the user's requested logic of explicit dispatch.
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="receptionist-agent",
                room=room_name,
            )
        )
        
        # 2. Dial the user via the Twilio SIP Trunk and bridge them to the room
        outbound_trunk_id = settings.SIP_OUTBOUND_TRUNK_ID
        if not outbound_trunk_id:
            logger.error("SIP_OUTBOUND_TRUNK_ID not found in settings.")
            raise ValueError("SIP_OUTBOUND_TRUNK_ID is missing")

        logger.info(f"Dialing {phone_number} using trunk {outbound_trunk_id}...")
        
        await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=room_name,
                sip_trunk_id=outbound_trunk_id,
                sip_call_to=phone_number,
                participant_identity=f"customer-{phone_number}",
            )
        )
        
        logger.info("Call initiated successfully.")
        
    except Exception as e:
        logger.error(f"Failed to trigger call: {e}")
        raise e
    finally:
        await lkapi.aclose()

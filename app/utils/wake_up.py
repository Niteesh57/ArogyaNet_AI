import httpx
import logging
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

async def wake_up_huggingface():
    """
    Ping the Hugging Face Space URL in the background to wake it up.
    This prevents cold starts for user interactions involving AI inference.
    """
    if not settings.HUGGINGFACE_SPACE:
        return
        
    try:
        async with httpx.AsyncClient() as client:
            # Send a simple GET request to wake the space
            await client.get(settings.HUGGINGFACE_SPACE, timeout=5.0)
            logger.info("Sent wake-up ping to HuggingFace Space.")
    except Exception as e:
        logger.warning(f"Failed to wake up HuggingFace Space: {e}")

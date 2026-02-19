import logging
import os
import httpx
from typing import Optional
from app.core.config import settings
logger = logging.getLogger(__name__)

# Base URL for the HF Space
# Adjust if the user provided a different one, but they said "nagireddy5/lifehealth-v1" space.
# The endpoint is likely https://nagireddy5-lifehealth-v1.hf.space
SPACE_URL = settings.HUGGINGFACE_SPACE

class MedVQA:
    def __init__(self):
        self.base_url = SPACE_URL
        self.timeout = 120.0 # Increased timeout for streaming/gen
        logger.info(f"MedVQA initialized with base URL: {self.base_url}")

    async def answer_question(self, question: str, image_path: Optional[str] = None):
        """
        Sends query to /agent/vision endpoint (Streaming Response).
        Request Body: {"prompt": "...", "image_url": "..."}
        Yields chunks of text.
        """
        endpoint = f"{self.base_url}/agent/vision"
        
        payload = {"prompt": question}
        if image_path and image_path.startswith("http"):
            payload["image_url"] = image_path

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # The endpoint returns a StreamingResponse (text/plain)
                # Pass data as JSON body
                async with client.stream("POST", endpoint, json=payload) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_text():
                        yield chunk
            except Exception as e:
                logger.error(f"MedVQA Error: {e}")
                yield f"Error connecting to AI Agent: {e}"

class MedASR:
    def __init__(self):
        self.base_url = SPACE_URL
        self.timeout = 60.0

    async def transcribe(self, audio_data: bytes, filename: str = "audio.wav") -> str:
        """
        Sends audio bytes as a file upload to /agent/speech.
        """
        endpoint = f"{self.base_url}/agent/speech"
        
        # Prepare multipart/form-data
        files = {"file": (filename, audio_data, "audio/wav")}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(endpoint, files=files)
                resp.raise_for_status()
                data = resp.json()
                return data.get("transcription", "")
            except Exception as e:
                logger.error(f"MedASR Error: {e}")
                return ""

class MedSigLIP:
    def __init__(self):
        self.base_url = SPACE_URL
        self.timeout = 30.0

    async def predict_text(self, image_url: str, candidates: list[str]) -> dict:
        """
        Zero-shot classification.
        Request Body: {"image_url": "...", "candidates": [...]}
        """
        endpoint = f"{self.base_url}/agent/siglip/text"
        payload = {
            "image_url": image_url,
            "candidates": candidates
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Send as JSON body
                resp = await client.post(endpoint, json=payload)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f"MedSigLIP Error: {e}")
                return {}

# Singletons
llm_instance = None
medasr_instance = None
siglip_instance = None

def get_vqa_chain():
    global llm_instance
    if llm_instance is None:
        llm_instance = MedVQA()
    return llm_instance

def get_medasr_chain():
    global medasr_instance
    if medasr_instance is None:
        medasr_instance = MedASR()
    return medasr_instance
    
def get_siglip_model():
    global siglip_instance
    if siglip_instance is None:
        siglip_instance = MedSigLIP()
    return siglip_instance





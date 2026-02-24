import logging
import os
import re
import httpx
from typing import Optional
from app.core.config import settings
logger = logging.getLogger(__name__)

# Base URL for the HF Space
# Endpoint: https://nagireddy5-lifehealth-v1.hf.space
SPACE_URL = settings.HUGGINGFACE_SPACE


class MedVQA:
    """Generic Medical Vision Question Answering via /agent/vision (MedGemma base)."""

    def __init__(self, endpoint: str = "/agent/vision"):
        self.base_url = SPACE_URL
        self.endpoint_path = endpoint
        self.timeout = 120.0
        logger.info(f"MedVQA initialized → {self.base_url}{self.endpoint_path}")

    async def answer_question(self, question: str, image_path: Optional[str] = None):
        """
        Sends query to the vision endpoint (StreamingResponse / text/plain).
        Request Body: {"prompt": "...", "image_url": "..."}
        Yields chunks of text.
        """
        endpoint = f"{self.base_url}{self.endpoint_path}"

        payload = {"prompt": question, "image_url": ""}
        if image_path and image_path.startswith("http"):
            payload["image_url"] = image_path

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream("POST", endpoint, json=payload) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_text():
                        yield chunk
            except Exception as e:
                logger.error(f"MedVQA Error ({self.endpoint_path}): {e}")
                yield f"Error connecting to AI Agent: {e}"


class MedSkinIndia(MedVQA):
    """
    Indian Skin Disease Specialist powered by MedGemma + Indian Skin LoRA.
    Routes to /agent/skin-india on the HF Space.
    Inherits all vision streaming logic from MedVQA.
    """

    def __init__(self):
        super().__init__(endpoint="/agent/skin-india")
        logger.info("MedSkinIndia specialist initialized.")


class MedASR:
    """Medical Automatic Speech Recognition via /agent/speech."""

    def __init__(self):
        self.base_url = SPACE_URL
        self.timeout = 60.0

    async def transcribe(self, audio_data: bytes, filename: str = "audio.wav") -> str:
        """
        Sends audio bytes as a multipart file upload to /agent/speech.
        Returns transcription string.
        """
        endpoint = f"{self.base_url}/agent/speech"
        files = {"file": (filename, audio_data, "audio/wav")}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(endpoint, files=files)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data.get("transcription", "")
                
                # Clean out the CTC blank tokens and special EOS tags
                clean_text = raw_text.replace("<epsilon>", "").replace("</s>", "").replace("<pad>", "")
                
                # Use regex to remove duplicate adjacent words (caused by CTC alignment overlap)
                clean_text = re.sub(r'\b(\w+)( \1\b)+', r'\1', clean_text)
                
                # Strip extra whitespace
                clean_text = " ".join(clean_text.split())

                return clean_text
            except Exception as e:
                logger.error(f"MedASR Error: {e}")
                return ""


class MedSigLIP:
    """Medical image zero-shot classification via /agent/siglip/text."""

    def __init__(self):
        self.base_url = SPACE_URL
        self.timeout = 30.0

    async def predict_text(self, image_url: str, candidates: list[str]) -> dict:
        """
        Zero-shot classification.
        Request Body: {"image_url": "...", "candidates": [...]}
        Returns: {"prediction": "...", "confidence": 0.95}
        """
        endpoint = f"{self.base_url}/agent/siglip/text"
        payload = {"image_url": image_url, "candidates": candidates}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(endpoint, json=payload)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f"MedSigLIP Error: {e}")
                return {}


class MedHEAR:
    """
    Health Acoustic Representations (HeAR) via /agent/hear/embed.
    Uploads an audio file and returns a 1D embedding vector capturing
    acoustic health patterns (coughs, breathing, cardiac sounds).
    """

    def __init__(self):
        self.base_url = SPACE_URL
        self.timeout = 60.0

    async def embed(self, audio_data: bytes, filename: str = "audio.wav") -> list[float]:
        """
        Uploads audio bytes to /agent/hear/embed.
        Returns a float embedding vector (shape: [1, D] flattened to list).
        Returns an empty list on failure.
        """
        endpoint = f"{self.base_url}/agent/hear/embed"
        files = {"file": (filename, audio_data, "audio/wav")}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(endpoint, files=files)
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                # Response is [[...]] (batch of 1), flatten to 1D
                if embeddings and isinstance(embeddings[0], list):
                    return embeddings[0]
                return embeddings
            except Exception as e:
                logger.error(f"MedHEAR Error: {e}")
                return []


# ── Singletons ──────────────────────────────────────────────────────────────

_vqa_instance = None
_medasr_instance = None
_siglip_instance = None
_skin_instance = None
_hear_instance = None


def get_vqa_chain() -> MedVQA:
    global _vqa_instance
    if _vqa_instance is None:
        _vqa_instance = MedVQA()
    return _vqa_instance


def get_medasr_chain() -> MedASR:
    global _medasr_instance
    if _medasr_instance is None:
        _medasr_instance = MedASR()
    return _medasr_instance


def get_siglip_model() -> MedSigLIP:
    global _siglip_instance
    if _siglip_instance is None:
        _siglip_instance = MedSigLIP()
    return _siglip_instance


def get_skin_chain() -> MedSkinIndia:
    """Returns the Indian Skin Specialist (MedGemma + LoRA) singleton."""
    global _skin_instance
    if _skin_instance is None:
        _skin_instance = MedSkinIndia()
    return _skin_instance


def get_hear_model() -> MedHEAR:
    """Returns the HeAR acoustic embedding model singleton."""
    global _hear_instance
    if _hear_instance is None:
        _hear_instance = MedHEAR()
    return _hear_instance





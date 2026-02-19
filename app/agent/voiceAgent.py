"""
Voice Agent - Medical Speech-to-Text using Remote MedASR
WebSocket endpoint to receive audio, transcribe using remote HF Space.
"""
import io
import logging
import base64
import wave
from app.agent.LLM.llm import get_medasr_chain

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000

async def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribe raw audio bytes (WAV / raw PCM) to text using Remote MedASR.
    Wraps PCM in WAV container if needed, then uploads as file.
    """
    medasr = get_medasr_chain()
    
    # ─── 1. Ensure Audio is WAV ───
    final_wav_bytes = audio_bytes
    
    # Simple check for RIFF header
    if not audio_bytes.startswith(b'RIFF'):
        # Assume Raw 16-bit PCM @ 16kHz
        # Wrap in WAV header
        try:
            with io.BytesIO() as wav_io:
                with wave.open(wav_io, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2) # 16-bit
                    wav_file.setframerate(SAMPLE_RATE)
                    wav_file.writeframes(audio_bytes)
                final_wav_bytes = wav_io.getvalue()
        except Exception as e:
            logger.error(f"Failed to wrap PCM in WAV: {e}")
            return ""

    if len(final_wav_bytes) < 100:
        return ""

    # ─── 2. Call Remote API (File Upload) ───
    try:
        # Pass bytes directly, llm.py handles multipart upload
        return await medasr.transcribe(final_wav_bytes, filename="speech.wav")
    except Exception as e:
        logger.error(f"Remote transcription error: {e}")
        return ""




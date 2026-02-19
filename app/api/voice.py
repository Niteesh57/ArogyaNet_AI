from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, UploadFile, File
import logging
from app.agent.voiceAgent import transcribe_audio

logger = logging.getLogger(__name__)

router = APIRouter()


import traceback

@router.post("/transcribe")
async def transcribe_file(file: UploadFile = File(...)):
    """
    Transcribe a full audio file (WAV/WebM/MP3) sent as form-data.
    """
    try:
        audio_bytes = await file.read()
        logger.info(f"Received audio file of size: {len(audio_bytes)} bytes")
        text = await transcribe_audio(audio_bytes)
        return {"text": text}
    except Exception as e:
        logger.error(f"File transcription error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}


@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    WebSocket endpoint for real-time medical speech-to-text.

    Protocol:
    ─────────
    1. Client connects to  ws://<host>/api/v1/voice/ws/transcribe
    2. Client sends audio chunks as **binary** WebSocket frames 
       (WAV or raw 16-bit PCM @ 16 kHz).
    3. Server transcribes each chunk and sends back a JSON message:
       { "type": "transcription", "text": "...", "chunk_index": N }
    4. Client sends a **text** message "END" to signal end of session.
    5. Server replies with the full conversation transcript:
       { "type": "final", "full_transcript": "...", "total_chunks": N }
    6. Connection is closed.
    """
    await websocket.accept()
    logger.info("Voice WebSocket connection accepted.")

    conversation_chunks: list[str] = []
    chunk_index = 0

    try:
        while True:
            # Receive message (can be binary audio or text control command)
            message = await websocket.receive()

            # ── Text control messages ──
            if "text" in message:
                text_msg = message["text"].strip().upper()
                if text_msg == "END":
                    # Send full transcript and close
                    full_transcript = " ".join(conversation_chunks)
                    await websocket.send_json({
                        "type": "final",
                        "full_transcript": full_transcript,
                        "total_chunks": len(conversation_chunks),
                    })
                    logger.info(
                        f"Session ended. {len(conversation_chunks)} chunks transcribed."
                    )
                    break
                elif text_msg == "PING":
                    await websocket.send_json({"type": "pong"})
                    continue
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown command: {text_msg}. Send audio as binary or 'END' to finish.",
                    })
                    continue

            # ── Binary audio data ──
            if "bytes" in message:
                audio_data: bytes = message["bytes"]

                if len(audio_data) < 100:
                    # Too small to be meaningful audio
                    await websocket.send_json({
                        "type": "error",
                        "message": "Audio chunk too small. Send at least 0.5s of audio.",
                    })
                    continue

                try:
                    transcribed_text = await transcribe_audio(audio_data)
                    conversation_chunks.append(transcribed_text)
                    chunk_index += 1

                    await websocket.send_json({
                        "type": "transcription",
                        "text": transcribed_text,
                        "chunk_index": chunk_index,
                    })
                    logger.info(
                        f"Chunk {chunk_index} transcribed: {transcribed_text[:80]}..."
                    )

                except Exception as e:
                    logger.error(f"Transcription error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Transcription failed: {str(e)}",
                    })

    except WebSocketDisconnect:
        logger.info("Voice WebSocket disconnected by client.")
    except Exception as e:
        logger.error(f"Voice WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Server error: {str(e)}",
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

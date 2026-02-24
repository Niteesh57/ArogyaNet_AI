import json
import httpx
from google import genai
from google.genai import types
from app.core.config import settings
from app.agent.LLM.llm import get_skin_chain

# Configure Gemini client
client = None
if settings.GOOGLE_API_KEY:
    client = genai.Client(api_key=settings.GOOGLE_API_KEY)


async def stream_medical_summary(image_url: str, use_skin_specialist: bool = False):
    """
    Analyzes a medical image and streams a summary as SSE events.

    Two modes:
    - use_skin_specialist=False (default): General medical report / lab report / prescription.
      Uses Google Gemini Vision directly for best document understanding.
    - use_skin_specialist=True: Indian skin/dermatology condition analysis.
      Routes to the HF Space /agent/skin-india endpoint (MedGemma + Indian Skin LoRA).

    SSE Event types:
      {"type": "token", "content": "..."}
      {"type": "done"}
      {"type": "error", "message": "..."}
    """
    if use_skin_specialist:
        yield f"data: {json.dumps({'type': 'status', 'message': 'Routing to Indian Skin Specialist (MedGemma + LoRA)...'})}\n\n"

        # Build a specialized dermatology prompt
        skin_prompt = (
            "You are an expert Indian dermatologist. "
            "Analyze the provided skin image and give a detailed clinical assessment. "
            "Include: "
            "1. Description of visible lesions (color, shape, distribution, texture). "
            "2. Most likely diagnosis (with differential diagnoses). "
            "3. Recommended lab investigations or tests if needed. "
            "4. Suggested treatment approach (topical/systemic). "
            "5. Urgency level (routine / urgent / emergency). "
            "Consider Indian skin types (Fitzpatrick III-VI) and common tropical dermatological conditions."
        )

        skin_chain = get_skin_chain()
        full_response = ""

        try:
            async for chunk in skin_chain.answer_question(question=skin_prompt, image_path=image_url):
                if chunk:
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            print(f"Error in skin specialist: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    else:
        # ── General mode: Gemini Vision (lab reports, prescriptions, X-rays) ──
        try:
            # 1. Download the image
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url)
                response.raise_for_status()
                image_data = response.content

            # 2. Setup Gemini Model
            model_name = settings.GENERAL_MODEL or "gemini-3-flash-preview"

            # 3. Create prompt
            system_prompt = """You are an Expert Medical Document Analyst.
Your task is to analyze the provided image, which could be a doctor's handwritten prescription, a clinical note, or a laboratory blood report.

Goals:
1. Summarize the content clearly.
2. If it's a doctor's note, describe the symptoms mentioned and the prescribed solution/medications.
3. If it's a lab report, highlight any critical values or results that are outside the normal range.
4. Interpret handwriting as accurately as possible.
5. Provide truth-based values from the document.

Output Format:
- Use Markdown for clarity (Headers, Bullet points).
- Start with a "Summary" section.
- Include a "Critical Findings" section if any abnormalities are detected.
- Conclude with a "Recommendations" section based strictly on the document's content.

Keep the tone professional and informative.
"""

            # 4. Generate content and stream
            contents = [
                system_prompt,
                types.Part.from_bytes(data=image_data, mime_type="image/jpeg")
            ]

            response = client.models.generate_content_stream(
                model=model_name,
                contents=contents
            )

            for chunk in response:
                if chunk.text:
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk.text})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            print(f"Error in stream_medical_summary: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

import json
import httpx
import google.generativeai as genai
from app.core.config import settings

# Configure Gemini
if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

async def stream_medical_summary(image_url: str):
    """
    Analyzes a medical report or doctor's note from an image and streams a summary using Gemini 1.5.
    Identifies critical values and suggested solutions.
    """
    try:
        # 1. Download the image
        async with httpx.AsyncClient() as client:
            response = await client.get(image_url)
            response.raise_for_status()
            image_data = response.content
            
        # 2. Setup Gemini Model
        model_name = settings.GENERAL_MODEL or "gemini-1.5-flash"
        model = genai.GenerativeModel(model_name)
        
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
            {"mime_type": "image/jpeg", "data": image_data}
        ]
        
        response = model.generate_content(contents, stream=True)
        
        for chunk in response:
            if chunk.text:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.text})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
    except Exception as e:
        print(f"Error in stream_medical_summary: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

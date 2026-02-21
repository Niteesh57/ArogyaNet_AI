import json
import httpx
import google.generativeai as genai
from typing import List, Dict, Any
from app.core.config import settings

# Configure Gemini
if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

async def populate_event_data(image_url: str, keys: List[str]) -> Dict[str, Any]:
    """
    Analyzes a form image and extracts values for the provided keys using Gemini 1.5.
    Returns a dictionary of key-value pairs.
    """
    try:
        # 1. Download the image
        async with httpx.AsyncClient() as client:
            response = await client.get(image_url)
            response.raise_for_status()
            image_data = response.content
            
        # 2. Setup Gemini Model with structured output configuration
        model_name = settings.GENERAL_MODEL or "gemini-1.5-flash"
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"response_mime_type": "application/json"}
        )
        
        # 3. Create prompt
        keys_str = ", ".join(keys)
        prompt = f"""You are an Expert Data Extraction Agent. 
Your task is to analyze the provided image of a form and extract the values for exactly the keys listed below.
Provide the output ONLY as a JSON object where the keys are exactly as requested and the values are what you find in the form.
If a value is not found or unclear, return null for that key.

Requested Keys:
{keys_str}

Output Format:
{{
    "key1": "value1",
    "key2": "value2",
    ...
}}
"""
        # 4. Generate content
        # model.generate_content can take a list containing the prompt and image data
        contents = [
            prompt,
            {"mime_type": "image/jpeg", "data": image_data}
        ]
        
        response = model.generate_content(contents)
        
        # 5. Parse and return JSON
        if response and response.text:
            return json.loads(response.text)
        else:
            return {key: None for key in keys}
            
    except Exception as e:
        print(f"Error in populate_event_data: {e}")
        return {"error": str(e)}

from typing import TypedDict, Optional, List, Dict
import logging
import json
import asyncio
import base64
import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from tavily import TavilyClient
from langchain_groq import ChatGroq

from app.core.config import settings
from app.agent.LLM.llm import get_vqa_chain, get_medasr_chain, get_siglip_model
from app.utils.pdf import extract_text_from_pdf_url

# Configure Logging
logger = logging.getLogger("deep-research-agent")

# --- 1. STATE DEFINITION ---
class ResearchState(TypedDict):
    # Inputs
    image_url: Optional[str]
    audio_url: Optional[str]
    pdf_url: Optional[str]
    vision_prompt: Optional[str]
    
    # Extracted Findings
    audio_transcription: str
    image_findings: str
    siglip_label: str
    pdf_content: str
    
    # Research
    tavily_results: str
    
    # Output
    final_report: str

# --- 2. NODES (WORKERS) ---

async def process_audio(state: ResearchState):
    """
    Downloads audio from URL and transcribes it using MedASR.
    """
    if not state.get("audio_url"):
        return {"audio_transcription": "No audio provided."}
    
    try:
        audio_url = state["audio_url"]
        logger.info(f"Processing Audio: {audio_url}")
        
        # Download audio first (MedASR needs file upload now)
        async with httpx.AsyncClient() as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            audio_bytes = resp.content
            
        medasr = get_medasr_chain()
        # Upload as 'speech.wav' - MedASR will handle it
        transcription = await medasr.transcribe(audio_bytes, filename="patient_audio.wav")
        
        if not transcription:
            transcription = "Audio processing failed or silent."
            
        return {"audio_transcription": transcription}
    except Exception as e:
        logger.error(f"Audio processing error: {e}")
        return {"audio_transcription": f"Error: {str(e)}"}

async def process_image(state: ResearchState):
    """
    Analyzes image using MedVQA (Streaming -> Full Text) and MedSigLIP.
    """
    if not state.get("image_url"):
        return {"image_findings": "No image provided.", "siglip_label": "N/A"}
        
    image_url = state["image_url"]
    prompt = state.get("vision_prompt", "Describe the medical findings in detail.")
    
    findings = ""
    label = "N/A"
    
    # 1. MedVQA
    try:
        llm_vqa = get_vqa_chain()
        # Consume the stream to get full text
        async for chunk in llm_vqa.answer_question(question=prompt, image_path=image_url):
            findings += chunk
    except Exception as e:
        findings = f"Error in MedVQA: {e}"
        
    # 2. MedSigLIP (Optional labels)
    try:
        siglip = get_siglip_model()
        # Example candidates
        candidates = ["Normal", "Fracture", "Pneumonia", "Infection", "Tumor", "Hemorrhage"]
        result = await siglip.predict_text(image_url=image_url, candidates=candidates)
        label = result.get("prediction", "N/A")
    except Exception as e:
        logger.warning(f"SigLIP error: {e}")
        
    return {"image_findings": findings, "siglip_label": label}

async def process_pdf(state: ResearchState):
    """
    Extracts text from PDF URL.
    """
    if not state.get("pdf_url"):
        return {"pdf_content": "No PDF provided."}
        
    try:
        text = await extract_text_from_pdf_url(state["pdf_url"])
        return {"pdf_content": text[:10000]} # Limit context
    except Exception as e:
        return {"pdf_content": f"Error extracting PDF: {e}"}

async def deep_research(state: ResearchState):
    """
    Uses Tavily to find medical context based on findings.
    """
    query_parts = []
    
    # Add High Confidence Findings
    if state.get("siglip_label") and state["siglip_label"] != "N/A":
        query_parts.append(f"{state['siglip_label']} treatment guidelines")
        
    if state.get("image_findings") and len(state["image_findings"]) > 20:
        # Extract keywords or just use the first sentence?
        # Let's simple ask about the findings
        query_parts.append(f"medical consensus on {state['image_findings'][:100]}")
        
    if state.get("audio_transcription") and "No audio" not in state["audio_transcription"]:
         query_parts.append(f"symptoms: {state['audio_transcription'][:100]}")
         
    if not query_parts:
        if state.get("vision_prompt"):
             query_parts.append(state["vision_prompt"])
        else:
             return {"tavily_results": "No sufficient data to research."}
             
    query = " ".join(query_parts)
    logger.info(f"Tavily Search Query: {query}")
    
    try:
        # Use official Tavily Python Client
        tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        # max_results=1 to keep it concise
        results = tavily_client.search(query=query, max_results=1, search_depth="basic")
        
        formatted_results = ""
        # response['results'] is a list of dicts: [{'title':..., 'url':..., 'content':...}]
        for res in results.get("results", []):
            formatted_results += f"- **[{res['title']}]({res['url']})**: {res['content'][:300]}...\n"
            
        return {"tavily_results": formatted_results}
    except Exception as e:
        logger.error(f"Tavily error: {e}")
        return {"tavily_results": f"Research failed: {e}"}

async def generate_final_report(state: ResearchState):
    return {"final_report": "Report generated in stream."}

workflow = StateGraph(ResearchState)
workflow.add_node("process_audio", process_audio)
workflow.add_node("process_image", process_image)
workflow.add_node("process_pdf", process_pdf)
workflow.add_node("deep_research", deep_research)

workflow.add_edge(START, "process_audio")
workflow.add_edge(START, "process_image")
workflow.add_edge(START, "process_pdf")

workflow.add_edge("process_audio", "deep_research")
workflow.add_edge("process_image", "deep_research")
workflow.add_edge("process_pdf", "deep_research")

workflow.add_edge("deep_research", END)

app_graph = workflow.compile()


async def run_deep_research(
    image_url: Optional[str] = None,
    audio_url: Optional[str] = None,
    pdf_url: Optional[str] = None,
    vision_prompt: Optional[str] = None
):
    """
    Async generator that runs the graph and yields SSE events.
    """
    
    inputs = {
        "image_url": image_url,
        "audio_url": audio_url,
        "pdf_url": pdf_url,
        "vision_prompt": vision_prompt,
        "audio_transcription": "",
        "image_findings": "",
        "siglip_label": "",
        "pdf_content": "",
        "tavily_results": "",
        "final_report": ""
    }
    
    yield f"data: {json.dumps({'type': 'status', 'message': 'Starting Research...'})}\n\n"
    
    final_state = inputs.copy()
    
    async for output in app_graph.astream(inputs):
        for node_name, node_output in output.items():
            final_state.update(node_output)
            
            if node_name == "process_audio":
                yield f"data: {json.dumps({'type': 'status', 'message': 'Audio Transcribed.'})}\n\n"
            elif node_name == "process_image":
                yield f"data: {json.dumps({'type': 'status', 'message': 'Image Analyzed.'})}\n\n"
            elif node_name == "process_pdf":
                yield f"data: {json.dumps({'type': 'status', 'message': 'PDF Processed.'})}\n\n"
            elif node_name == "deep_research":
                yield f"data: {json.dumps({'type': 'status', 'message': 'Research Completed.'})}\n\n"
                
    yield f"data: {json.dumps({'type': 'status', 'message': 'Synthesizing Report...'})}\n\n"
    
    # Using ChatGroq (Llama 3 70B for strong reasoning)
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=settings.GROQ_API_KEY,
        temperature=0.3
    )
    
    # Simplified System Prompt
    system_prompt = """You are a Medical Research Assistant.
Create a concise medical report from the provided inputs (Audio, Image, PDF) and research.
Structure:
1. Patient Overview (Symptoms)
2. Findings (Image/PDF)
3. Research Insight (Brief)
4. Recommendations
Keep it professional but brief.
"""

    # Construct User Prompt dynamically
    prompt_parts = ["-- INPUTS --"]
    
    if image_url:
        prompt_parts.append(f"[Image URL]: {image_url}")
    
    # Only include Audio if valid
    if final_state.get('audio_transcription') and "No audio" not in final_state.get('audio_transcription', ''):
        prompt_parts.append(f"\n-- AUDIO TRANSCRIPT --\n{final_state['audio_transcription']}")
        
    # Only include Image Analysis if valid
    if final_state.get('image_findings') and "No image" not in final_state.get('image_findings', ''):
        label = final_state.get('siglip_label', 'N/A')
        prompt_parts.append(f"\n-- IMAGE ANALYSIS (Label: {label}) --\n{final_state['image_findings']}")
        
    # Only include PDF if valid
    if final_state.get('pdf_content') and "No PDF" not in final_state.get('pdf_content', ''):
        prompt_parts.append(f"\n-- PDF CONTENT --\n{final_state['pdf_content']}")
        
    # Include Research
    if final_state.get('tavily_results'):
        prompt_parts.append(f"\n-- MEDICAL RESEARCH --\n{final_state['tavily_results']}")
        
    user_prompt = "\n".join(prompt_parts)
    
    try:
        # logger.info("Starting Groq LLM Stream...")
        async for chunk in llm.astream([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]):
            token = chunk.content
            if token:
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                
    except Exception as e:
        logger.error(f"Groq Stream Error: {e}")
        yield f"data: {json.dumps({'type': 'status', 'message': f'Error generating report: {e}'})}\n\n"

        
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
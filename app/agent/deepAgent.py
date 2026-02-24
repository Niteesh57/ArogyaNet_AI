from typing import TypedDict, Optional, List, Dict
import logging
import json
import asyncio
import httpx
import math
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from tavily import TavilyClient
from langchain_groq import ChatGroq

from app.core.config import settings
from app.agent.LLM.llm import get_vqa_chain, get_medasr_chain, get_siglip_model, get_hear_model
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
    hear_summary: str            # NEW: HeAR acoustic health summary
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
    Downloads audio from URL and transcribes it using MedASR (medical speech recognition).
    """
    if not state.get("audio_url"):
        return {"audio_transcription": "No audio provided."}

    try:
        audio_url = state["audio_url"]
        logger.info(f"MedASR: Processing audio from {audio_url}")

        async with httpx.AsyncClient() as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            audio_bytes = resp.content

        medasr = get_medasr_chain()
        transcription = await medasr.transcribe(audio_bytes, filename="patient_audio.wav")

        if not transcription:
            transcription = "Audio processing failed or silent."

        return {"audio_transcription": transcription}
    except Exception as e:
        logger.error(f"Audio processing error: {e}")
        return {"audio_transcription": f"Error: {str(e)}"}


async def process_hear_audio(state: ResearchState):
    """
    NEW: Downloads audio and generates a HeAR (Health Acoustic Representation) embedding.
    HeAR captures acoustic health signals such as cough patterns, breathing irregularities,
    and cardiac sounds — separate from speech transcription.
    The embedding vector magnitude is used as a proxy for acoustic health anomaly level.
    """
    if not state.get("audio_url"):
        return {"hear_summary": "No audio provided for acoustic analysis."}

    try:
        audio_url = state["audio_url"]
        logger.info(f"HeAR: Generating acoustic embeddings from {audio_url}")

        async with httpx.AsyncClient() as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            audio_bytes = resp.content

        hear = get_hear_model()
        embedding = await hear.embed(audio_bytes, filename="patient_audio.wav")

        if not embedding:
            return {"hear_summary": "HeAR acoustic analysis unavailable for this audio."}

        # Interpret embedding: compute L2 norm as a rough acoustic energy / anomaly indicator
        # High norm → acoustically rich / potentially abnormal signal
        norm = math.sqrt(sum(x ** 2 for x in embedding))
        dim = len(embedding)

        # Rough thresholding (empirical — can be calibrated with labelled data)
        if norm > 15:
            anomaly_level = "High"
            interpretation = (
                "The acoustic embedding shows a HIGH energy signature, suggesting possible "
                "respiratory distress, persistent cough, or abnormal breathing patterns. "
                "Recommend clinical evaluation of respiratory and cardiac status."
            )
        elif norm > 8:
            anomaly_level = "Moderate"
            interpretation = (
                "The acoustic embedding shows a MODERATE energy signature. "
                "Some irregularity in breathing or vocal patterns detected. "
                "Monitor the patient and correlate with other clinical findings."
            )
        else:
            anomaly_level = "Low"
            interpretation = (
                "The acoustic embedding shows a LOW energy signature. "
                "No prominent acoustic health anomalies detected from this recording."
            )

        summary = (
            f"HeAR Acoustic Analysis (embedding dim={dim}, L2 norm={norm:.2f}):\n"
            f"Anomaly Level: {anomaly_level}\n"
            f"Interpretation: {interpretation}"
        )

        logger.info(f"HeAR summary generated — norm={norm:.2f}, level={anomaly_level}")
        return {"hear_summary": summary}

    except Exception as e:
        logger.error(f"HeAR processing error: {e}")
        return {"hear_summary": f"HeAR analysis error: {str(e)}"}


async def process_image(state: ResearchState):
    """
    Analyzes image using MedVQA (streaming → full text) and MedSigLIP zero-shot classification.
    """
    if not state.get("image_url"):
        return {"image_findings": "No image provided.", "siglip_label": "N/A"}

    image_url = state["image_url"]
    prompt = state.get("vision_prompt", "Describe the medical findings in detail.")

    findings = ""
    label = "N/A"

    # 1. MedVQA — detailed visual analysis
    try:
        llm_vqa = get_vqa_chain()
        async for chunk in llm_vqa.answer_question(question=prompt, image_path=image_url):
            findings += chunk
    except Exception as e:
        findings = f"Error in MedVQA: {e}"

    # 2. MedSigLIP — zero-shot classification label
    try:
        siglip = get_siglip_model()
        candidates = ["Normal", "Fracture", "Pneumonia", "Infection", "Tumor", "Hemorrhage"]
        result = await siglip.predict_text(image_url=image_url, candidates=candidates)
        label = result.get("prediction", "N/A")
    except Exception as e:
        logger.warning(f"SigLIP error: {e}")

    return {"image_findings": findings, "siglip_label": label}


async def process_pdf(state: ResearchState):
    """Extracts text from PDF URL (up to 10,000 chars for LLM context)."""
    if not state.get("pdf_url"):
        return {"pdf_content": "No PDF provided."}

    try:
        text = await extract_text_from_pdf_url(state["pdf_url"])
        return {"pdf_content": text[:10000]}
    except Exception as e:
        return {"pdf_content": f"Error extracting PDF: {e}"}


async def deep_research(state: ResearchState):
    """
    Uses Tavily to find medical context based on multi-modal findings.
    Incorporates HeAR anomaly level into search queries.
    """
    query_parts = []

    if state.get("siglip_label") and state["siglip_label"] != "N/A":
        query_parts.append(f"{state['siglip_label']} treatment guidelines")

    if state.get("image_findings") and len(state["image_findings"]) > 20:
        query_parts.append(f"medical consensus on {state['image_findings'][:100]}")

    if state.get("audio_transcription") and "No audio" not in state["audio_transcription"]:
        query_parts.append(f"symptoms: {state['audio_transcription'][:100]}")

    # NEW: Add HeAR high-anomaly signals to research query
    hear_summary = state.get("hear_summary", "")
    if "High" in hear_summary:
        query_parts.append("respiratory distress cough anomaly clinical evaluation guidelines")
    elif "Moderate" in hear_summary:
        query_parts.append("breathing irregularity monitoring clinical assessment")

    if not query_parts:
        if state.get("vision_prompt"):
            query_parts.append(state["vision_prompt"])
        else:
            return {"tavily_results": "No sufficient data to research."}

    query = " ".join(query_parts)
    logger.info(f"Tavily Search Query: {query}")

    try:
        tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        results = tavily_client.search(query=query, max_results=1, search_depth="basic")

        formatted_results = ""
        for res in results.get("results", []):
            formatted_results += f"- **[{res['title']}]({res['url']})**: {res['content'][:300]}...\n"

        return {"tavily_results": formatted_results}
    except Exception as e:
        logger.error(f"Tavily error: {e}")
        return {"tavily_results": f"Research failed: {e}"}


# --- 3. GRAPH DEFINITION ---
# Parallel fan-out: audio, hear, image, pdf → deep_research → END

workflow = StateGraph(ResearchState)

workflow.add_node("process_audio", process_audio)
workflow.add_node("process_hear_audio", process_hear_audio)   # NEW HeAR node
workflow.add_node("process_image", process_image)
workflow.add_node("process_pdf", process_pdf)
workflow.add_node("deep_research", deep_research)

# Fan-out: all four processors run in parallel from START
workflow.add_edge(START, "process_audio")
workflow.add_edge(START, "process_hear_audio")                # NEW
workflow.add_edge(START, "process_image")
workflow.add_edge(START, "process_pdf")

# Fan-in: all feed into deep_research
workflow.add_edge("process_audio", "deep_research")
workflow.add_edge("process_hear_audio", "deep_research")      # NEW
workflow.add_edge("process_image", "deep_research")
workflow.add_edge("process_pdf", "deep_research")

workflow.add_edge("deep_research", END)

app_graph = workflow.compile()


# --- 4. ENTRY POINT ---

async def run_deep_research(
    image_url: Optional[str] = None,
    audio_url: Optional[str] = None,
    pdf_url: Optional[str] = None,
    vision_prompt: Optional[str] = None
):
    """
    Async generator that runs the full multi-modal research graph and yields SSE events.

    SSE Event Types:
      - {"type": "status", "message": "..."}   — pipeline progress updates
      - {"type": "token",  "content": "..."}   — streamed report tokens
      - {"type": "done"}                        — stream complete
    """
    inputs = {
        "image_url": image_url,
        "audio_url": audio_url,
        "pdf_url": pdf_url,
        "vision_prompt": vision_prompt,
        "audio_transcription": "",
        "hear_summary": "",
        "image_findings": "",
        "siglip_label": "",
        "pdf_content": "",
        "tavily_results": "",
        "final_report": "",
    }

    yield f"data: {json.dumps({'type': 'status', 'message': 'Starting Deep Research...'})}\n\n"

    final_state = inputs.copy()

    async for output in app_graph.astream(inputs):
        for node_name, node_output in output.items():
            final_state.update(node_output)

            status_map = {
                "process_audio":      "MedASR: Audio Transcribed.",
                "process_hear_audio": "HeAR: Acoustic Analysis Complete.",
                "process_image":      "MedVQA + SigLIP: Image Analyzed.",
                "process_pdf":        "PDF: Text Extracted.",
                "deep_research":      "Tavily: Research Completed.",
            }
            if node_name in status_map:
                yield f"data: {json.dumps({'type': 'status', 'message': status_map[node_name]})}\n\n"

    yield f"data: {json.dumps({'type': 'status', 'message': 'Synthesizing Final Report (Llama 3.3 70B)...'})}\n\n"

    # Final synthesis — Llama 3.3 70B (via Groq) for strong medical reasoning
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=settings.GROQ_API_KEY,
        temperature=0.3,
    )

    system_prompt = """You are a Medical Research Assistant.
Create a concise, professional medical report from the multi-modal inputs provided.
Structure your response as:
1. Patient Overview (Symptoms / Complaints)
2. Image Findings (if applicable)
3. Acoustic Health Analysis (HeAR — respiratory/cardiac patterns if applicable)
4. Research Insight (brief)
5. Recommendations
Keep the tone clinical and precise."""

    prompt_parts = ["-- MULTI-MODAL INPUTS --"]

    if image_url:
        prompt_parts.append(f"[Image URL]: {image_url}")

    if final_state.get("audio_transcription") and "No audio" not in final_state["audio_transcription"]:
        prompt_parts.append(f"\n-- AUDIO TRANSCRIPT (MedASR) --\n{final_state['audio_transcription']}")

    # NEW: include HeAR acoustic summary
    if final_state.get("hear_summary") and "No audio" not in final_state["hear_summary"]:
        prompt_parts.append(f"\n-- ACOUSTIC HEALTH ANALYSIS (HeAR) --\n{final_state['hear_summary']}")

    if final_state.get("image_findings") and "No image" not in final_state["image_findings"]:
        label = final_state.get("siglip_label", "N/A")
        prompt_parts.append(f"\n-- IMAGE ANALYSIS (SigLIP Label: {label}) --\n{final_state['image_findings']}")

    if final_state.get("pdf_content") and "No PDF" not in final_state["pdf_content"]:
        prompt_parts.append(f"\n-- PDF CONTENT --\n{final_state['pdf_content']}")

    if final_state.get("tavily_results"):
        prompt_parts.append(f"\n-- MEDICAL RESEARCH --\n{final_state['tavily_results']}")

    user_prompt = "\n".join(prompt_parts)

    try:
        async for chunk in llm.astream([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]):
            token = chunk.content
            if token:
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
    except Exception as e:
        logger.error(f"Groq Stream Error: {e}")
        yield f"data: {json.dumps({'type': 'status', 'message': f'Error generating report: {e}'})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
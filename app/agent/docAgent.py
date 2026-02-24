from typing import TypedDict, Annotated, Sequence, Union
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import logging
import io
import httpx
from PIL import Image

from app.agent.LLM.llm import get_vqa_chain
from app.utils.pdf import extract_text_from_pdf_url

logger = logging.getLogger(__name__)

# State Definition
class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    document_url: str
    document_type: str # 'pdf' or 'image'
    extracted_text: str # For PDFs
    local_image_path: str # For Images (downloaded temp path)
    long_term_memories: str # Context from long-term memory

# Nodes
async def load_document(state: AgentState):
    """
    Downloads document from URL. Detects type.
    If PDF: Extract text.
    If Image: Download to temp file.
    """
    url = state["document_url"]
    logger.info(f"Loading document: {url}")
    
    # Simple extension check (improve with checking content-type header if needed)
    lower_url = url.lower()
    
    if ".pdf" in lower_url:
        text = await extract_text_from_pdf_url(url)
        return {"document_type": "pdf", "extracted_text": text}
    else:
        # Assume Image
        # Download to temp file for MedVQA to read
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            image_bytes = resp.content
            
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".jpg") # MedVQA might expect extension
        with os.fdopen(fd, 'wb') as tmp:
            tmp.write(image_bytes)
            
        return {"document_type": "image", "local_image_path": path}

async def analyze_document(state: AgentState):
    """
    Calls MedVQA with the document context.
    """
    llm = get_vqa_chain()
    
    # Get the latest question
    question = state["messages"][-1].content
    memories = state.get("long_term_memories", "")
    
    response_text = ""
    
    # Prepend memories to question for context
    context_prefix = ""
    if memories:
        context_prefix = f"User Context (Memories):\n{memories}\n\n"

    if state.get("document_type") == "pdf":
        # Text Context
        context = state.get("extracted_text", "")
        # Limit context size if needed? MedGemma has 8k context probably.
        prompt = f"System: You are an expert medical AI. Analyze the following medical report text and answer the user's question.\n\n{context_prefix}Report Context:\n{context[:6000]}\n\nUser Question: {question}"
        
        response_text = await llm.answer_question(question=prompt, image_path=None)
        
    else:
        # Image Context
        path = state.get("local_image_path")
        document_url = state.get("document_url")
        
        final_question = f"{context_prefix}Question: {question}"

        # Check if original URL is an image (simple check or rely on previous detection)
        if state.get("document_type") == "image":
             response_text = await llm.answer_question(question=final_question, image_path=document_url)
        else:
             # Fallback or if for some reason we only have local path
             response_text = await llm.answer_question(question=final_question, image_path=path)
        
        # Cleanup temp file? Maybe later or rely on OS cleanup
        try:
            import os
            os.remove(path)
        except: pass

    return {"messages": [HumanMessage(content=response_text)]}

# Graph Construction
workflow = StateGraph(AgentState)

workflow.add_node("load_document", load_document)
workflow.add_node("analyze_document", analyze_document)

workflow.set_entry_point("load_document")
workflow.add_edge("load_document", "analyze_document")
workflow.add_edge("analyze_document", END)

checkpointer = MemorySaver()

app = workflow.compile(checkpointer=checkpointer)

from app.agent.Tools.MemeoryTools import add_long_term_memory, get_long_term_memories

async def analyze_medical_document(user_id: str, document_url: str, question: str, appointment_id: str, db=None):
    """
    Entry point to run the agent. Returns a stream of tokens/messages if possible, 
    or the final string.
    Saves the interaction to AppointmentChat.
    """
    # Fetch Long Term Memories if DB is available
    memories_str = ""
    if db:
        memories = await get_long_term_memories(user_id, db)
        if memories:
            memories_str = "\n".join([f"- {m}" for m in memories])

    inputs = {
        "messages": [HumanMessage(content=question)],
        "document_url": document_url,
        "document_type": "", # will be filled by load_document
        "extracted_text": "",
        "local_image_path": "",
        "long_term_memories": memories_str
    }
    
    # Use appointment_id as thread_id to share context between doctor and patient
    thread_id = str(appointment_id) if appointment_id else user_id
    
    logger.info(f"Analyzing document with thread_id: {thread_id}, appointment_id: {appointment_id}, user_id: {user_id}")
    
    # Run the graph (Load Document Phase)
    # We run up to 'analyze_document' but we can't easily stream OUT of a node in a graph invoke.
    # So we will use the 'load_document' node logic, then manually call LLM streaming.
    
    # 1. Load Document info first
    # We can reuse the node function if we construct state manually, or just use the logic.
    # Reusing the node function is cleaner but it expects state.
    
    doc_state = {
        "document_url": document_url,
        "messages": [HumanMessage(content=question)],
        "long_term_memories": memories_str
    }
    
    # Execute load_document node logic
    try:
        loaded_data = await load_document(doc_state)
        doc_state.update(loaded_data)
    except Exception as e:
        logger.error(f"Error loading document: {e}")
        yield f"Error loading document: {e}"
        return

    # 2. Prepare Prompt (Logic from analyze_document node)
    llm = get_vqa_chain()
    context_prefix = ""
    if memories_str:
        context_prefix = f"User Context (Memories):\n{memories_str}\n\n"

    prompt = ""
    image_path = None
    
    if doc_state.get("document_type") == "pdf":
        context = doc_state.get("extracted_text", "")
        prompt = f"System: You are an expert medical AI. Analyze the following medical report text and answer the user's question.\n\n{context_prefix}Report Context:\n{context[:6000]}\n\nUser Question: {question}"
    else:
        # Image
        path = doc_state.get("local_image_path")
        # MedVQA (remote) prefers URL
        image_path = document_url if document_url else path
        prompt = f"{context_prefix}Question: {question}"

    # 3. Stream LLM Response
    full_response = ""
    try:
        import json
        async for chunk in llm.answer_question(question=prompt, image_path=image_path):
            full_response += chunk
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return

    # Cleanup temp file if needed
    if doc_state.get("local_image_path"):
        try:
             import os
             os.remove(doc_state["local_image_path"])
        except: pass

    # 4. Save to DB (AppointmentChat) & Long Term Memory
    if db:
        # Save memory?
        lower_q = question.lower()
        if lower_q.startswith("remember") or "save this info" in lower_q:
             await add_long_term_memory(user_id, question, db)

        if appointment_id:
            try:
                from app.models.appointment_chat import AppointmentChat
                chat_entry = AppointmentChat(
                    appointment_id=appointment_id,
                    user_id=user_id,
                    message=question,
                    response=full_response,
                    document_url=document_url
                )
                db.add(chat_entry)
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to save chat history: {e}")

import google.generativeai as genai
from pinecone import Pinecone
from app.core.config import settings

# Initialize Pinecone
pc = Pinecone(api_key=settings.PINECONE_API_KEY)
index = pc.Index("lifehealth")

# Configure Gemini
if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

def get_embedding(text: str, input_type: str = "passage") -> list[float]:
    """
    Generate embedding using Pinecone Inference (to match index model).
    Model: llama-text-embed-v2 (1024 dimensions)
    """
    try:
        # Check if text is empty
        if not text or not text.strip():
            return []
            
        embedding_response = pc.inference.embed(
            model="llama-text-embed-v2",
            inputs=[text],
            parameters={
                "input_type": input_type, 
                "truncate": "END"
            }
        )
        return embedding_response[0]['values']
    except Exception as e:
        print(f"Embedding Error: {e}")
        return []

async def upsert_check(
    check_id: str,
    check_text: str,
    category: str,
    hospital_id: str,
    medication: str = None,
    lab_test: str = None
):
    """
    Embed and store a check/insight in Pinecone with metadata.
    """
    try:
        # Construct rich context for embedding
        content_to_embed = f"{check_text} [Category: {category}]"
        
        # If hospital-specific data is present (medication/labs), include them in the embedding context
        if hospital_id:
             if medication:
                 content_to_embed += f" [Medication: {medication}]"
             if lab_test:
                 content_to_embed += f" [Lab Test: {lab_test}]"
        
        # input_type="passage" for storing docs
        embedding = get_embedding(content_to_embed, input_type="passage")
        
        if not embedding:
            return {"status": "error", "message": "Failed to generate embedding."}

        metadata = {
            "check_text": check_text,
            "category": category,
            "hospital_id": hospital_id,
            "medication": medication or "",
            "lab_test": lab_test or ""
        }
        
        index.upsert(vectors=[(check_id, embedding, metadata)])
        return {"status": "success", "message": f"Check {check_id} upserted."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def retrieve_checks(
    query: str,
    hospital_id: str,
    user_hospital_id: str,
    category: str = None,
    top_k: int = 3,
    strict_hospital: bool = False
):
    """
    Retrieve relevant checks/insights based on query with enhanced details.
    
    Args:
        hospital_id: The hospital to prioritize/target for search.
        user_hospital_id: The ID of the user performing the search (for privacy check).
        
    Logic:
    1. Search within the TARGET hospital (`hospital_id`).
    2. If results < top_k AND strict_hospital is False, Search globally.
    3. PRIVACY: Only show meds/labs if `match.hospital_id == user_hospital_id`.
    """
    try:
        # input_type="query" for search queries
        query_embedding = get_embedding(query, input_type="query")
        
        if not query_embedding:
            return []

        # 1. Primary Search: Target Hospital
        filter_primary = {"hospital_id": hospital_id}
        if category:
            filter_primary["category"] = category
            
        results_primary = index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            filter=filter_primary
        )
        
        matches = []
        seen_ids = set()
        
        def process_match(match, source_label):
            metadata = match['metadata']
            match_hospital_id = metadata.get('hospital_id')
            
            # PRIVACY CHECK: Only show sensitive data if it belongs to the user's hospital
            is_own_hospital = (match_hospital_id == user_hospital_id)
            
            meds = metadata.get('medication', '')
            labs = metadata.get('lab_test', '')
            
            if not is_own_hospital:
                meds = "Restricted (Different Hospital)"
                labs = "Restricted (Different Hospital)"
                if source_label != "Same Hospital":
                     source_label = "Global Experience" # Generic label for others
            
            return {
                "score": match['score'],
                "check_text": metadata.get('check_text'),
                "id": match['id'],
                "medication": meds,
                "lab_test": labs,
                "source": source_label,
                "hospital_id": match_hospital_id
            }

        # Process Primary Results
        for match in results_primary.get('matches', []):
            # For primary search, match_hospital_id SHOULD be hospital_id.
            # Label depends on whether target == user
            label = "Same Hospital" if hospital_id == user_hospital_id else "Targeted Hospital"
            processed = process_match(match, label)
            matches.append(processed)
            seen_ids.add(match['id'])
            
        # 2. Secondary Search: Different Hospital (If needed and NOT strict)
        if not strict_hospital and len(matches) < top_k:
            remaining_k = top_k - len(matches)
            
            # Filter specifically excludes target hospital
            filter_secondary = {"hospital_id": {"$ne": hospital_id}}
            if category:
                filter_secondary["category"] = category
                
            results_secondary = index.query(
                vector=query_embedding,
                top_k=remaining_k, # Fetch just enough to fill
                include_metadata=True,
                filter=filter_secondary
            )
            
            # Process Secondary Results
            for match in results_secondary.get('matches', []):
                if match['id'] not in seen_ids:
                    processed = process_match(match, "Global Experience")
                    matches.append(processed)
            
        return matches
    except Exception as e:
        return {"status": "error", "message": str(e)}


import json

async def stream_expert_answer(
    query: str,
    hospital_id: str,
    user_hospital_id: str,
    category: str = None,
    strict_hospital: bool = False
):
    """
    Stream answer based on query and retrieved context.
    Uses GENERAL_MODEL (Gemini) for generation.
    Returns SSE events: type=token (text) and type=metadata (meds/labs).
    """
    try:
        # 1. Retrieve Context
        relevant_checks = await retrieve_checks(
            query=query,
            hospital_id=hospital_id,
            user_hospital_id=user_hospital_id,
            category=category,
            top_k=5,
            strict_hospital=strict_hospital
        )
        
        # 2. Format Context & Collect Metadata
        context_str = ""
        unique_meds = set()
        unique_labs = set()
        
        if not relevant_checks:
            context_str = "No specific past experiences found for this query."
        else:
            for i, check in enumerate(relevant_checks, 1):
                source_type = check.get('source', 'Unknown')
                content = check.get('check_text', '')
                meds = check.get('medication', '')
                labs = check.get('lab_test', '')
                
                context_str += f"\n--- Experience {i} ({source_type}) ---\n"
                context_str += f"Insight: {content}\n"
                
                # Only show meds/labs in context if not restricted
                if "Restricted" not in meds and meds:
                    context_str += f"Medication Used: {meds}\n"
                    # Add to metadata collection (split by comma if needed)
                    for m in meds.split(','):
                        if m.strip(): unique_meds.add(m.strip())
                        
                if "Restricted" not in labs and labs:
                    context_str += f"Lab Tests Ordered: {labs}\n"
                    # Add to metadata collection
                    for l in labs.split(','):
                        if l.strip(): unique_labs.add(l.strip())

        # 3. Generate Answer
        system_prompt = f"""You are an Expert Medical AI assistant for doctors.
Use the following retrieved experiences from senior doctors to answer the user's query.
If the experience is from the SAME hospital, you can recommend the specific medications and lab tests mentioned.
If the experience is from a DIFFERENT hospital (Global), summarize the clinical insight/approach but DO NOT invent medications if they are hidden/restricted.
Provide a concise, professional medical answer.

Context:
{context_str}

User Query: {query}
"""
        model_name = settings.GENERAL_MODEL or "gemini-1.5-flash"
        model = genai.GenerativeModel(model_name)
        
        response = model.generate_content(system_prompt, stream=True)
        
        for chunk in response:
            if chunk.text:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.text})}\n\n"
        
        # 4. Stream Metadata (Medications and Labs)
        yield f"data: {json.dumps({'type': 'metadata', 'medications': list(unique_meds), 'lab_tests': list(unique_labs)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


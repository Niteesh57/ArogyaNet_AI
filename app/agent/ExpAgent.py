import google.generativeai as genai
from pinecone import Pinecone
from app.core.config import settings

# Initialize Pinecone
pc = Pinecone(api_key=settings.PINECONE_API_KEY)
index = pc.Index("lifehealth")

# pc is already initialized above
# Remove genai configuration if not used for other things (or keep if needed for other agents, but not for embedding here)

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
    category: str = None,
    top_k: int = 3
):
    """
    Retrieve relevant checks/insights based on query with enhanced details.
    Logic:
    1. Search within the SAME hospital. (Show full data)
    2. If results < top_k, Search globally (excluding current hospital). (Hide meds/labs)
    """
    try:
        # input_type="query" for search queries
        query_embedding = get_embedding(query, input_type="query")
        
        if not query_embedding:
            return []

        # 1. Primary Search: Same Hospital
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
        
        # Process Primary Results (Full Data)
        for match in results_primary.get('matches', []):
            metadata = match['metadata']
            matches.append({
                "score": match['score'],
                "check_text": metadata.get('check_text'),
                "id": match['id'],
                "medication": metadata.get('medication', ''),
                "lab_test": metadata.get('lab_test', ''),
                "source": "Same Hospital"
            })
            seen_ids.add(match['id'])
            
        # 2. Secondary Search: Different Hospital (If needed)
        if len(matches) < top_k:
            remaining_k = top_k - len(matches)
            
            # Filter specifically excludes current hospital
            filter_secondary = {"hospital_id": {"$ne": hospital_id}}
            if category:
                filter_secondary["category"] = category
                
            results_secondary = index.query(
                vector=query_embedding,
                top_k=remaining_k, # Fetch just enough to fill
                include_metadata=True,
                filter=filter_secondary
            )
            
            # Process Secondary Results (Restricted Data)
            for match in results_secondary.get('matches', []):
                if match['id'] not in seen_ids: # Redundant check but safe
                    metadata = match['metadata']
                    matches.append({
                        "score": match['score'],
                        "check_text": metadata.get('check_text'),
                        "id": match['id'],
                        "medication": "Restricted (Different Hospital)", # Hide Sensitive Data
                        "lab_test": "Restricted (Different Hospital)",   # Hide Sensitive Data
                        "source": "Global Experience"
                    })
            
        return matches
    except Exception as e:
        return {"status": "error", "message": str(e)}


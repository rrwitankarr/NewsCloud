import json
import asyncio
from services.search import search_web_for_claim
from services.scraper import scrape_url
from services.embedding import chunk_text, retrieve_top_k_chunks, rerank_chunks
from services.llm import generate_verdict

async def run_verification_pipeline_sse(claim: str):
    """
    Executes the full AVeriTeC pipeline and yields SSE JSON events for progress.
    """
    yield json.dumps({"status": "processing", "message": f"Starting pipeline for claim: '{claim}'"})
    await asyncio.sleep(0.1)
    
    # 1. Search
    yield json.dumps({"status": "processing", "message": "Searching the web..."})
    search_results = search_web_for_claim(claim, max_results=5)
    urls = search_results["urls"]
    snippets = search_results["snippets"]
    
    if not urls:
        yield json.dumps({"status": "error", "message": "Failed to find any relevant search results to verify this claim."})
        return
    yield json.dumps({"status": "processing", "message": f"Found {len(urls)} URLs. Scraping content..."})
    await asyncio.sleep(0.1)
    
    # 2. Scrape & Chunk
    all_chunks = []
    for url in urls:
        text = scrape_url(url)
        if text:
            chunks = chunk_text(text)
            all_chunks.extend(chunks)
            
    yield json.dumps({"status": "processing", "message": f"Generated {len(all_chunks)} chunks of evidence."})
    await asyncio.sleep(0.1)
    
    top_5_chunks = []
    if all_chunks:
        # 3. Retrieve Top 50 (Bi-Encoder)
        yield json.dumps({"status": "processing", "message": "Retrieving top chunks (Bi-Encoder)..."})
        top_50_chunks = retrieve_top_k_chunks(claim, all_chunks, top_k=50)
        await asyncio.sleep(0.1)
        
        # 4. Re-rank Top 5 (Cross-Encoder)
        yield json.dumps({"status": "processing", "message": "Re-ranking top chunks (Cross-Encoder)..."})
        top_5_chunks = rerank_chunks(claim, top_50_chunks, top_k=5)
        await asyncio.sleep(0.1)
    
    # Combine search snippets (which often contain the direct answer) with the deep-dive semantic chunks
    final_evidence = [f"Search Result Summary: {s}" for s in snippets] + top_5_chunks
    
    if not final_evidence:
        yield json.dumps({"status": "error", "message": "Failed to gather any evidence."})
        return
        
        # 5. Generate Verdict (LLM)
    yield json.dumps({
        "status": "processing",
        "message": "Generating verdict with Gemini..."
    })

    try:
        result = generate_verdict(
            claim,
            final_evidence
        )

    except Exception as e:

        # Defensive fallback in case an unexpected error
        # escapes the LLM service.
        print(f"Unexpected LLM pipeline error: {e}")

        result = {
            "verdict": None,
            "explanation": (
                "The AI verification service is temporarily "
                "unavailable. Supporting evidence was collected, "
                "but a complete AI verdict could not be generated."
            ),
            "verification_status": "degraded",
            "ai_available": False,
            "degradation_reason": "unexpected_llm_error",
        }

    # Attach evidence regardless of AI availability
    result["evidence"] = final_evidence
    result["urls"] = urls

    # Overall pipeline completed
    result["status"] = "complete"

    # Tell frontend how verification was performed
    if result.get("verification_status") == "degraded":
        result["message"] = (
            "Verification completed in degraded mode. "
            "Supporting evidence was collected, but AI "
            "verification is temporarily unavailable."
        )
    else:
        result["message"] = (
            "Verification completed successfully."
        )

    yield json.dumps(result)
    
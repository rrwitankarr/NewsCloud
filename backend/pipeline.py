import json
import asyncio

from services.search import search_web_for_claim
from services.scraper import scrape_url
from services.embedding import (
    chunk_text,
    retrieve_top_k_chunks,
    rerank_chunks
)
from services.llm import generate_verdict


async def run_verification_pipeline_sse(claim: str):
    """
    Executes the full AVeriTeC pipeline and yields SSE JSON events
    for progress.

    The final result contains:
        - verdict
        - explanation
        - evidence
        - urls
        - verification status
        - AI availability
    """

    # =========================================================
    # START
    # =========================================================

    yield json.dumps({
        "status": "processing",
        "message": f"Starting pipeline for claim: '{claim}'"
    })

    await asyncio.sleep(0.1)

    # =========================================================
    # 1. SEARCH
    # =========================================================

    yield json.dumps({
        "status": "processing",
        "message": "Searching the web..."
    })

    search_results = search_web_for_claim(
        claim,
        max_results=5
    )

    urls = search_results.get("urls", [])
    snippets = search_results.get("snippets", [])

    if not urls:
        yield json.dumps({
            "status": "error",
            "message": (
                "Failed to find any relevant search results "
                "to verify this claim."
            )
        })
        return

    yield json.dumps({
        "status": "processing",
        "message": (
            f"Found {len(urls)} URLs. "
            "Scraping content..."
        )
    })

    await asyncio.sleep(0.1)

    # =========================================================
    # 2. SCRAPE & CHUNK
    # =========================================================

    all_chunks = []

    for url in urls:

        try:
            text = scrape_url(url)

            if text:
                chunks = chunk_text(text)
                all_chunks.extend(chunks)

        except Exception as e:
            print(
                f"Failed to scrape {url}: {e}"
            )

    yield json.dumps({
        "status": "processing",
        "message": (
            f"Generated {len(all_chunks)} "
            "chunks of evidence."
        )
    })

    await asyncio.sleep(0.1)

    # =========================================================
    # 3. RETRIEVE TOP 50
    # =========================================================

    top_5_chunks = []

    if all_chunks:

        yield json.dumps({
            "status": "processing",
            "message": (
                "Retrieving top chunks "
                "(Bi-Encoder)..."
            )
        })

        try:

            top_50_chunks = retrieve_top_k_chunks(
                claim,
                all_chunks,
                top_k=50
            )

        except Exception as e:

            print(
                f"Bi-Encoder retrieval failed: {e}"
            )

            top_50_chunks = []

        await asyncio.sleep(0.1)

        # =====================================================
        # 4. RE-RANK TOP 5
        # =====================================================

        if top_50_chunks:

            yield json.dumps({
                "status": "processing",
                "message": (
                    "Re-ranking top chunks "
                    "(Cross-Encoder)..."
                )
            })

            try:

                top_5_chunks = rerank_chunks(
                    claim,
                    top_50_chunks,
                    top_k=5
                )

            except Exception as e:

                print(
                    f"Cross-Encoder re-ranking failed: {e}"
                )

                top_5_chunks = []

            await asyncio.sleep(0.1)

    # =========================================================
    # 5. BUILD FINAL EVIDENCE
    # =========================================================

    # Search snippets are useful because they often contain
    # the direct answer to the claim.
    search_evidence = [
        f"Search Result Summary: {snippet}"
        for snippet in snippets
        if snippet
    ]

    # Deep semantic evidence obtained through:
    #
    # Bi-Encoder -> Top 50
    # Cross-Encoder -> Top 5
    #
    deep_evidence = [
        chunk
        for chunk in top_5_chunks
        if chunk
    ]

    final_evidence = (
        search_evidence +
        deep_evidence
    )

    if not final_evidence:

        yield json.dumps({
            "status": "error",
            "message": "Failed to gather any evidence."
        })

        return

    # =========================================================
    # 6. GENERATE VERDICT
    # =========================================================

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

        print(
            f"Unexpected LLM pipeline error: {e}"
        )

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

    # =========================================================
    # 7. ATTACH EVIDENCE AND URLS
    # =========================================================

    # IMPORTANT:
    #
    # These two fields are what claims.py will save into
    # PostgreSQL.
    #
    # The next user will receive these from the database
    # instead of performing another web search.

    result["evidence"] = final_evidence

    result["urls"] = urls

    # =========================================================
    # 8. MARK PIPELINE COMPLETE
    # =========================================================

    result["status"] = "complete"

    # =========================================================
    # 9. VERIFICATION MESSAGE
    # =========================================================

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

    # =========================================================
    # 10. SEND FINAL RESULT
    # =========================================================

    yield json.dumps(result)
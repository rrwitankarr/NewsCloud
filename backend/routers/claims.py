import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

from services.embedding import get_bi_encoder
from pipeline import run_verification_pipeline_sse


router = APIRouter(prefix="/api/claims", tags=["claims"])

# ---------------------------------------------------------
# CACHE CONFIGURATION
# ---------------------------------------------------------

# Cached verification results are valid for 7 days.
CACHE_DURATION = timedelta(days=7)


# ---------------------------------------------------------
# HELPER: CHECK WHETHER A CACHED RESULT IS DEGRADED
# ---------------------------------------------------------

def is_degraded_cached_result(cached_claim) -> bool:
    """
    Determine whether an existing database record represents
    a temporary AI/API failure rather than a genuine verdict.

    Degraded results should never be reused from the cache.
    """

    explanation = (cached_claim.explanation or "").lower()

    degraded_markers = [
        "503",
        "429",
        "service unavailable",
        "temporarily unavailable",
        "high demand",
        "api error",
        "ai verification service",
        "gemini",
        "unexpected_llm_error",
        "degraded",
    ]

    return any(
        marker in explanation
        for marker in degraded_markers
    )


# ---------------------------------------------------------
# VERIFY CLAIM - SSE ENDPOINT
# ---------------------------------------------------------

@router.post("/verify/stream")
async def verify_claim_stream(
    request: Request,
    claim: schemas.ClaimRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):

    # -----------------------------------------------------
    # 1. GENERATE CLAIM EMBEDDING
    # -----------------------------------------------------

    bi_encoder = get_bi_encoder()

    embedding_tensor = bi_encoder.encode(
        claim.content,
        convert_to_tensor=True
    )

    embedding_list = embedding_tensor.cpu().numpy().tolist()


    # -----------------------------------------------------
    # 2. SEARCH DATABASE FOR SIMILAR CLAIM
    # -----------------------------------------------------

    similar_record = db.query(
        models.Claim,
        models.Claim.embedding.cosine_distance(
            embedding_list
        ).label("distance")
    ).order_by("distance").first()


    # -----------------------------------------------------
    # 3. SSE EVENT GENERATOR
    # -----------------------------------------------------

    async def event_generator():

        # =================================================
        # FAST PATH - DATABASE CACHE
        # =================================================

        if similar_record and similar_record.distance < 0.05:

            cached_claim = similar_record.Claim

            # -------------------------------------------------
            # 3A. CHECK CACHE AGE
            # -------------------------------------------------

            cache_is_fresh = True

            created_at = getattr(
                cached_claim,
                "created_at",
                None
            )

            if created_at is not None:

                # Handle timezone-aware timestamps safely.
                now = datetime.now(
                    created_at.tzinfo
                ) if created_at.tzinfo else datetime.utcnow()

                cache_age = now - created_at

                if cache_age > CACHE_DURATION:

                    cache_is_fresh = False

                    print(
                        "Cached verification expired "
                        f"({cache_age.days} days old). "
                        "Removing it from database."
                    )

                    db.delete(cached_claim)
                    db.commit()


            # -------------------------------------------------
            # 3B. CHECK WHETHER CACHE IS A DEGRADED RESULT
            # -------------------------------------------------

            cached_result_is_degraded = False

            # Only inspect the record if it hasn't already
            # been deleted because of expiration.
            if cache_is_fresh:

                cached_result_is_degraded = (
                    is_degraded_cached_result(cached_claim)
                )


            # -------------------------------------------------
            # 3C. DELETE OLD DEGRADED CACHE RECORD
            # -------------------------------------------------

            if cached_result_is_degraded:

                print(
                    "Found degraded/API-failure cache entry. "
                    "It will NOT be reused."
                )

                db.delete(cached_claim)
                db.commit()

                # Continue to live verification below.


            # -------------------------------------------------
            # 3D. REUSE VALID CACHE
            # -------------------------------------------------

            elif cache_is_fresh:

                print(
                    "Using valid cached verification result."
                )

                yield {
                    "data": json.dumps({
                        "status": "processing",
                        "message": (
                            "Fast Path: Found recent "
                            "verified claim in database!"
                        )
                    })
                }

                yield {
                    "data": json.dumps({
                        "claim_id": cached_claim.id,
                        "verdict": cached_claim.verdict,
                        "explanation": cached_claim.explanation,
                        "evidence": [],
                        "urls": ["Cached from Database"],
                        "status": "complete",

                        # Cached results are previous successful
                        # verification results.
                        "verification_status": "normal",
                        "ai_available": True
                    })
                }

                return


        # =================================================
        # SLOW PATH - LIVE VERIFICATION
        # =================================================

        print(
            "Running live verification pipeline..."
        )

        async for progress_json in run_verification_pipeline_sse(
            claim.content
        ):

            # -------------------------------------------------
            # CHECK WHETHER CLIENT DISCONNECTED
            # -------------------------------------------------

            if await request.is_disconnected():
                print(
                    "Client disconnected during verification."
                )
                break


            # -------------------------------------------------
            # PARSE PIPELINE EVENT
            # -------------------------------------------------

            data = json.loads(progress_json)


            # =================================================
            # VERIFICATION COMPLETE
            # =================================================

            if data.get("status") == "complete":

                # -------------------------------------------------
                # CHECK FOR DEGRADED VERIFICATION
                # -------------------------------------------------

                verification_status = data.get(
                    "verification_status"
                )

                ai_available = data.get(
                    "ai_available",
                    True
                )

                degradation_reason = data.get(
                    "degradation_reason"
                )

                is_degraded = (
                    verification_status == "degraded"
                    or ai_available is False
                    or degradation_reason is not None
                )


                # =================================================
                # DEGRADED RESULT
                # =================================================

                if is_degraded:

                    print(
                        "Verification completed in DEGRADED mode."
                    )

                    print(
                        "Degraded result will NOT be "
                        "saved to database."
                    )

                    # -------------------------------------------------
                    # IMPORTANT:
                    # Return the result to the frontend,
                    # but DO NOT save it to PostgreSQL.
                    # -------------------------------------------------

                    yield {
                        "data": json.dumps(data)
                    }

                    continue


                # =================================================
                # NORMAL RESULT
                # =================================================

                print(
                    "Verification completed normally. "
                    "Saving result to database."
                )

                new_claim = models.Claim(
                    content=claim.content,
                    embedding=embedding_list,
                    verdict=data.get("verdict"),
                    explanation=data.get("explanation"),
                )

                db.add(new_claim)
                db.commit()
                db.refresh(new_claim)


                # -------------------------------------------------
                # ATTACH DATABASE ID
                # -------------------------------------------------

                data["claim_id"] = new_claim.id

                # IMPORTANT:
                # No GEM is awarded at verification time.
                yield {
                    "data": json.dumps(data)
                }


            # =================================================
            # PROCESSING / INTERMEDIATE EVENT
            # =================================================

            else:

                yield {
                    "data": progress_json
                }


    # ---------------------------------------------------------
    # RETURN SSE RESPONSE
    # ---------------------------------------------------------

    return EventSourceResponse(
        event_generator()
    )
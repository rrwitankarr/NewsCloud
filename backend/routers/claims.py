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


router = APIRouter(
    prefix="/api/claims",
    tags=["claims"]
)


# =========================================================
# CACHE CONFIGURATION
# =========================================================

# Cached verification results are valid for 7 days.
CACHE_DURATION = timedelta(days=7)


# =========================================================
# HELPER: CHECK WHETHER A CACHED RESULT IS DEGRADED
# =========================================================

def is_degraded_cached_result(cached_claim) -> bool:
    """
    Determine whether an existing database record represents
    a temporary AI/API failure rather than a genuine verdict.

    Degraded results should never be reused from the cache.
    """

    explanation = (
        cached_claim.explanation or ""
    ).lower()

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


# =========================================================
# VERIFY CLAIM - SSE ENDPOINT
# =========================================================

@router.post("/verify/stream")
async def verify_claim_stream(
    request: Request,
    claim: schemas.ClaimRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    ),
):

    # =====================================================
    # 1. GENERATE CLAIM EMBEDDING
    # =====================================================

    bi_encoder = get_bi_encoder()

    embedding_tensor = bi_encoder.encode(
        claim.content,
        convert_to_tensor=True
    )

    embedding_list = (
        embedding_tensor
        .cpu()
        .numpy()
        .tolist()
    )

    # =====================================================
    # 2. SEARCH DATABASE FOR SIMILAR CLAIM
    # =====================================================

    similar_record = (
        db.query(
            models.Claim,
            models.Claim.embedding.cosine_distance(
                embedding_list
            ).label("distance")
        )
        .order_by("distance")
        .first()
    )

    # =====================================================
    # 3. SSE EVENT GENERATOR
    # =====================================================

    async def event_generator():

        # =================================================
        # FAST PATH - DATABASE CACHE
        # =================================================

        if (
            similar_record
            and similar_record.distance < 0.05
        ):

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
                now = (
                    datetime.now(
                        created_at.tzinfo
                    )
                    if created_at.tzinfo
                    else datetime.utcnow()
                )

                cache_age = (
                    now - created_at
                )

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
            # 3B. CHECK WHETHER CACHE IS DEGRADED
            # -------------------------------------------------

            cached_result_is_degraded = False

            # Only inspect the record if it hasn't already
            # been deleted because of expiration.

            if cache_is_fresh:

                cached_result_is_degraded = (
                    is_degraded_cached_result(
                        cached_claim
                    )
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
                    "Using valid cached verification result "
                    "including cached evidence."
                )

                # =================================================
                # LOAD SUPPORTING EVIDENCE FROM DATABASE
                # =================================================

                cached_evidence_rows = (
                    db.query(models.Evidence)
                    .filter(
                        models.Evidence.claim_id
                        == cached_claim.id
                    )
                    .order_by(
                        models.Evidence.id
                    )
                    .all()
                )

                # Convert database Evidence objects back into
                # the same format used by the live pipeline.
                cached_evidence = []

                for evidence_row in cached_evidence_rows:

                    if evidence_row.chunk_text:

                        cached_evidence.append(
                            evidence_row.chunk_text
                        )

                # =================================================
                # LOAD CACHED SOURCE URLS
                # =================================================

                cached_urls = []

                for evidence_row in cached_evidence_rows:

                    if (
                        evidence_row.source_url
                        and evidence_row.source_url
                        not in cached_urls
                    ):

                        cached_urls.append(
                            evidence_row.source_url
                        )

                # =================================================
                # CACHE PROGRESS MESSAGE
                # =================================================

                yield {
                    "data": json.dumps({
                        "status": "processing",
                        "message": (
                            "Fast Path: Found recent "
                            "verified claim in database. "
                            "Loading cached evidence..."
                        )
                    })
                }

                # =================================================
                # RETURN COMPLETE CACHED RESULT
                # =================================================

                yield {
                    "data": json.dumps({

                        # Database claim ID
                        "claim_id": cached_claim.id,

                        # Cached verdict
                        "verdict": cached_claim.verdict,

                        # Cached explanation
                        "explanation": (
                            cached_claim.explanation
                        ),

                        # IMPORTANT:
                        # Supporting evidence now comes
                        # from PostgreSQL.
                        "evidence": cached_evidence,

                        # IMPORTANT:
                        # Original source URLs also come
                        # from PostgreSQL.
                        "urls": cached_urls,

                        # Pipeline status
                        "status": "complete",

                        # This result came from cache.
                        "cached": True,

                        # Cached results are previous successful
                        # verification results.
                        "verification_status": "normal",

                        "ai_available": True,

                        # Useful for frontend display/debugging.
                        "message": (
                            "This claim was previously verified. "
                            "The verdict and supporting evidence "
                            "were retrieved from the database."
                        )
                    })
                }

                return

        # =========================================================
        # SLOW PATH - LIVE VERIFICATION
        # =========================================================

        print(
            "Running live verification pipeline..."
        )

        async for progress_json in (
            run_verification_pipeline_sse(
                claim.content
            )
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

            data = json.loads(
                progress_json
            )

            # =================================================
            # VERIFICATION COMPLETE
            # =================================================

            if data.get("status") == "complete":

                # -------------------------------------------------
                # CHECK FOR DEGRADED VERIFICATION
                # -------------------------------------------------

                verification_status = (
                    data.get(
                        "verification_status"
                    )
                )

                ai_available = (
                    data.get(
                        "ai_available",
                        True
                    )
                )

                degradation_reason = (
                    data.get(
                        "degradation_reason"
                    )
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
                        "Verification completed in "
                        "DEGRADED mode."
                    )

                    print(
                        "Degraded result will NOT be "
                        "saved to database."
                    )

                    # -------------------------------------------------
                    # IMPORTANT:
                    #
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
                    "Saving result and evidence to database."
                )

                # =================================================
                # CREATE CLAIM
                # =================================================

                new_claim = models.Claim(
                    content=claim.content,
                    embedding=embedding_list,
                    verdict=data.get(
                        "verdict"
                    ),
                    explanation=data.get(
                        "explanation"
                    ),
                )

                db.add(new_claim)

                # Flush so new_claim.id becomes available
                # before creating Evidence records.
                db.flush()

                # =================================================
                # SAVE SUPPORTING EVIDENCE
                # =================================================

                evidence_items = data.get(
                    "evidence",
                    []
                )

                urls = data.get(
                    "urls",
                    []
                )

                for index, evidence in enumerate(
                    evidence_items
                ):

                    # -------------------------------------------------
                    # Evidence is normally a string.
                    #
                    # This also safely handles dictionary-style
                    # evidence if the pipeline is changed later.
                    # -------------------------------------------------

                    if isinstance(
                        evidence,
                        str
                    ):

                        chunk_text = evidence

                    elif isinstance(
                        evidence,
                        dict
                    ):

                        chunk_text = (
                            evidence.get(
                                "text"
                            )
                            or evidence.get(
                                "chunk_text"
                            )
                            or str(evidence)
                        )

                    else:

                        chunk_text = str(
                            evidence
                        )

                    # -------------------------------------------------
                    # Associate search evidence with its URL.
                    #
                    # Deep semantic chunks may not have a direct
                    # URL association, so source_url remains None.
                    # -------------------------------------------------

                    source_url = None

                    if index < len(urls):

                        source_url = urls[index]

                    # -------------------------------------------------
                    # Create Evidence database record
                    # -------------------------------------------------

                    new_evidence = models.Evidence(
                        claim_id=new_claim.id,
                        source_url=source_url,
                        chunk_text=chunk_text,
                        similarity_score=None,
                    )

                    db.add(
                        new_evidence
                    )

                # =================================================
                # COMMIT CLAIM + EVIDENCE
                # =================================================

                db.commit()

                db.refresh(
                    new_claim
                )

                # =================================================
                # ATTACH DATABASE ID
                # =================================================

                data["claim_id"] = (
                    new_claim.id
                )

                # This is a fresh/live verification.
                data["cached"] = False

                # =================================================
                # NO GEM IS AWARDED AT VERIFICATION TIME
                # =================================================

                yield {
                    "data": json.dumps(
                        data
                    )
                }

            # =================================================
            # PROCESSING / INTERMEDIATE EVENT
            # =================================================

            else:

                yield {
                    "data": progress_json
                }

    # =========================================================
    # RETURN SSE RESPONSE
    # =========================================================

    return EventSourceResponse(
        event_generator()
    )
import os
import smtplib
import time
from email.message import EmailMessage
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from services.llm import genai
from publisher_contact_agent import publisher_contact_agent, fetch_page


router = APIRouter(prefix="/api/complaints", tags=["complaints"])


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class VerifySourceRequest(BaseModel):
    claim: str
    url: str


class VerifySourceResponse(BaseModel):
    match: bool
    message: str
    draft: str = ""
    complaint_id: Optional[int] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    contact_name: Optional[str] = None
    contact_type: Optional[str] = None
    contact_source_url: Optional[str] = None


class SendComplaintRequest(BaseModel):
    complaint_id: int
    draft: str


class SendComplaintResponse(BaseModel):
    success: bool
    message: str
    gem_awarded: bool = False


# ============================================================
# SMTP EMAIL
# ============================================================

def _smtp_send(
    recipient: str,
    subject: str,
    body: str,
    sender_name: str
) -> None:
    """Send an email using SMTP credentials supplied through environment variables."""

    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM") or username

    if not all([host, username, password, sender]):
        raise RuntimeError(
            "Email sending is not configured. Set SMTP_HOST, SMTP_USERNAME, "
            "SMTP_PASSWORD and SMTP_FROM in the backend .env file."
        )

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(msg)


# ============================================================
# LLM ERROR HANDLING
# ============================================================

def _is_temporary_llm_error(error: Exception) -> bool:
    """Return True for provider errors that are normally safe to retry."""

    error_text = str(error).upper()

    temporary_markers = (
        "503",
        "UNAVAILABLE",
        "429",
        "RESOURCE_EXHAUSTED",
        "RATE LIMIT",
        "TOO MANY REQUESTS",
        "HIGH DEMAND",
        "OVERLOADED",
        "TIMEOUT",
        "TIMED OUT",
    )

    return any(marker in error_text for marker in temporary_markers)


# ============================================================
# VERIFIED CLAIM
# ============================================================

def _get_verified_claim(
    db: Session,
    claim_text: str
) -> models.Claim:
    """
    Find the latest verified claim using normalized text.
    Only FALSE or MISLEADING claims can be reported.
    """

    normalized_text = " ".join(claim_text.split()).casefold()

    claim_records = (
        db.query(models.Claim)
        .filter(
            models.Claim.verdict.in_(("FALSE", "MISLEADING"))
        )
        .order_by(models.Claim.id.desc())
        .all()
    )

    claim_record = next(
        (
            record
            for record in claim_records
            if " ".join(record.content.split()).casefold()
            == normalized_text
        ),
        None
    )

    if not claim_record:
        raise HTTPException(
            status_code=400,
            detail=(
                "No matching FALSE or MISLEADING verified claim "
                "was found. Verify the exact same claim text first."
            )
        )

    return claim_record

# ============================================================
# DUPLICATE CHECK
# ============================================================

def _already_sent(
    db: Session,
    claim_id: int,
    source_url: str
) -> bool:

    return (
        db.query(models.Complaint.id)
        .filter(
            models.Complaint.claim_id == claim_id,
            models.Complaint.source_url == source_url,
            models.Complaint.is_sent.is_(True),
        )
        .first()
        is not None
    )


# ============================================================
# VERIFY SOURCE
# ============================================================

@router.post(
    "/verify-source",
    response_model=VerifySourceResponse
)
def verify_source(
    request: VerifySourceRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):

    claim = request.claim.strip()
    url = request.url.strip()

    # --------------------------------------------------------
    # The complaint flow starts only after the main verifier
    # has produced FALSE/MISLEADING.
    # --------------------------------------------------------

    claim_record = _get_verified_claim(
        db,
        claim
    )

    # --------------------------------------------------------
    # 1. Verify that the user-provided URL actually
    #    contains/supports the disputed claim.
    # --------------------------------------------------------

    try:
        page = fetch_page(url)

        if page.get("error") and not page.get("text"):
            raise Exception(page.get("error"))

        text = page.get("text", "")

        if not text:
            raise Exception(
                "Could not extract text from the URL."
            )

    except Exception as e:
        return VerifySourceResponse(
            match=False,
            message=f"Failed to verify the source URL: {str(e)}",
        )

    # --------------------------------------------------------
    # Gemini configuration
    # --------------------------------------------------------

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY not set"
        )

    client = genai.Client(
        api_key=api_key
    )

    text_snippet = text[:20000]

    prompt = f"""
You are an expert fact-checker and content analyzer.
Determine whether the article text makes, supports, or contains the specified claim.

Claim being disputed: "{claim}"

Article Text:
{text_snippet}

Answer with EXACTLY YES or NO.
"""

    MAX_RETRIES = 3

    # --------------------------------------------------------
    # LLM verification with retry
    # --------------------------------------------------------

    for attempt in range(MAX_RETRIES):

        try:

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )

            answer = response.text.strip().upper()

            if "YES" in answer:
                # YES means the URL contains/supports the claim.
                #
                # Do NOT return here.
                #
                # Continue to:
                # 1. check duplicates
                # 2. run publisher_contact_agent()
                # 3. create Complaint DB row
                # 4. return complaint_id + contact_email
                #
                # Returning here would prevent the frontend
                # from receiving complaint_id/contact_email.
                pass

            else:
                # NO is handled after the retry loop below.
                pass

        except Exception as e:

            temporary_error = _is_temporary_llm_error(e)

            if temporary_error and attempt < MAX_RETRIES - 1:
                # Exponential backoff: 2s, then 4s.
                time.sleep(
                    2 ** (attempt + 1)
                )
                continue

            if temporary_error:
                # Graceful degradation:
                # never guess a verification result.
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "LLM_TEMPORARILY_UNAVAILABLE",
                        "message": (
                            "Source verification is temporarily unavailable "
                            "because the AI verification service is busy. "
                            "Please try again in a moment. "
                            "No complaint was created and no GEM was awarded."
                        ),
                        "retryable": True,
                        "retry_after_seconds": 10,
                    },
                    headers={
                        "Retry-After": "10"
                    },
                )

            # Other unexpected verification errors:
            # fail safely.
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "LLM_VERIFICATION_FAILED",
                    "message": (
                        "The source could not be verified at this time. "
                        "Please try again later. "
                        "No complaint was created and no GEM was awarded."
                    ),
                    "retryable": False
                }
            )

    # --------------------------------------------------------
    # Check final LLM answer
    # --------------------------------------------------------

    if "YES" not in answer:
        return VerifySourceResponse(
            match=False,
            message=(
                "The provided URL does not appear to contain "
                "or support the disputed claim."
            )
        )

    # --------------------------------------------------------
    # 2. IMPORTANT:
    #    Check exact claim + exact source URL before drafting.
    #
    #    Same claim on a different URL is allowed.
    # --------------------------------------------------------

    if _already_sent(
        db,
        claim_record.id,
        url
    ):
        return VerifySourceResponse(
            match=False,
            message=(
                "This exact claim from this exact source URL "
                "has already been reported by another user. "
                "No GEM is awarded."
            ),
        )

    # --------------------------------------------------------
    # 3. Find publisher contact dynamically
    #    using the standalone Python agent.
    # --------------------------------------------------------

    try:

        contact_result = publisher_contact_agent(
            url
        )

        contact = contact_result.get(
            "contact",
            {}
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Publisher contact search failed: {str(e)}",
        )

    recipient = contact.get(
        "contact_email"
    )

    # --------------------------------------------------------
    # No usable publisher email
    # --------------------------------------------------------

    if not recipient:

        # We deliberately do not invent an email address.
        return VerifySourceResponse(
            match=False,
            message=(
                "The source contains the disputed claim, "
                "but the publisher-contact agent could not "
                "find a usable email address. "
                "No complaint draft was created. "
                f"Contact type: "
                f"{contact.get('contact_type', 'unavailable')}."
            ),
            contact_phone=contact.get(
                "contact_phone"
            ),
            contact_name=contact.get(
                "contact_name"
            ),
            contact_type=contact.get(
                "contact_type"
            ),
            contact_source_url=contact.get(
                "contact_source_url"
            ),
        )

    # --------------------------------------------------------
    # 4. Generate complaint draft only after:
    #
    #    - source validation
    #    - duplicate check
    #    - contact discovery
    # --------------------------------------------------------

    draft = (
        f"Dear Editor/Publisher,\n\n"
        f"I am writing to report a potentially false or misleading "
        f"claim published in the following article:\n"
        f"{url}\n\n"
        f"The disputed claim is:\n"
        f"\"{claim}\"\n\n"
        f"Our verification process found this claim to be "
        f"{claim_record.verdict}. "
        f"The supplied source URL was also checked and "
        f"contains/supports the disputed claim.\n\n"
        f"Please review the article and consider issuing an "
        f"appropriate correction or clarification.\n\n"
        f"Sincerely,\n"
        f"{current_user.username}"
    )

    # --------------------------------------------------------
    # Store the draft as an unsent complaint.
    #
    # Unsent rows do not block other users.
    # --------------------------------------------------------

    complaint = models.Complaint(
        user_id=current_user.id,
        claim_id=claim_record.id,
        source_url=url,
        recipient_email=recipient,
        draft_text=draft,
        is_sent=False,
    )

    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    # --------------------------------------------------------
    # Return complaint information to frontend
    # --------------------------------------------------------

    return VerifySourceResponse(
        match=True,
        message=(
            "Source verified. Publisher contact found and "
            "complaint draft prepared for your review."
        ),
        draft=draft,
        complaint_id=complaint.id,
        contact_email=recipient,
        contact_phone=contact.get(
            "contact_phone"
        ),
        contact_name=contact.get(
            "contact_name"
        ),
        contact_type=contact.get(
            "contact_type"
        ),
        contact_source_url=contact.get(
            "contact_source_url"
        ),
    )


# ============================================================
# SEND COMPLAINT
# ============================================================

@router.post(
    "/send",
    response_model=SendComplaintResponse
)
def send_complaint(
    request: SendComplaintRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):

    # --------------------------------------------------------
    # Find complaint belonging to current user
    # --------------------------------------------------------

    complaint = (
        db.query(models.Complaint)
        .filter(
            models.Complaint.id == request.complaint_id,
            models.Complaint.user_id == current_user.id,
        )
        .first()
    )

    if not complaint:
        raise HTTPException(
            status_code=404,
            detail="Complaint draft not found."
        )

    # --------------------------------------------------------
    # Already sent
    # --------------------------------------------------------

    if complaint.is_sent:
        return SendComplaintResponse(
            success=True,
            message=(
                "This complaint has already been sent. "
                "No additional GEM was awarded."
            ),
            gem_awarded=False,
        )

    # --------------------------------------------------------
    # Re-check exact pair immediately before external dispatch
    # --------------------------------------------------------

    duplicate = (
        db.query(models.Complaint.id)
        .filter(
            models.Complaint.id != complaint.id,
            models.Complaint.claim_id == complaint.claim_id,
            models.Complaint.source_url == complaint.source_url,
            models.Complaint.is_sent.is_(True),
        )
        .first()
    )

    if duplicate:

        db.delete(complaint)
        db.commit()

        return SendComplaintResponse(
            success=False,
            message=(
                "This exact claim + source URL was already "
                "reported by another user. No GEM is awarded."
            ),
            gem_awarded=False,
        )

    # --------------------------------------------------------
    # Save user's final edited draft.
    #
    # Do not mark it sent yet.
    # --------------------------------------------------------

    complaint.draft_text = request.draft
    db.commit()

    # --------------------------------------------------------
    # Send email
    # --------------------------------------------------------

    try:

        subject = "Misinformation / Correction Request"

        _smtp_send(
            complaint.recipient_email,
            subject,
            request.draft,
            current_user.username,
        )

    except Exception as e:

        # Failed dispatch:
        # no GEM and complaint remains unsent.
        return SendComplaintResponse(
            success=False,
            message=(
                f"Email was not sent, so no GEM was awarded. "
                f"{str(e)}"
            ),
            gem_awarded=False,
        )

    # ========================================================
    # SUCCESSFUL EMAIL DISPATCH
    # ========================================================
    #
    # ONLY successful external dispatch earns +1 GEM.
    #
    # We keep the existing reward exactly as +1.
    #
    # Additionally, create a GemTransaction so that monthly
    # GEM earnings can be calculated later.
    # ========================================================

    complaint.is_sent = True

    # Existing lifetime GEM score
    current_user.gem_score += 1

    # Monthly GEM transaction
    gem_transaction = models.GemTransaction(
        user_id=current_user.id,
        amount=1,
        reason="Verified misinformation complaint",
    )

    db.add(gem_transaction)

    # Save complaint + lifetime GEM + transaction together.
    db.commit()

    # --------------------------------------------------------
    # Successful response
    # --------------------------------------------------------

    return SendComplaintResponse(
        success=True,
        message="Complaint email sent successfully. +1 GEM awarded.",
        gem_awarded=True,
    )
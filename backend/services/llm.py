import os
import time
from datetime import datetime
from google import genai


def is_retryable_error(error):
    """
    Determines whether the Gemini error is temporary and worth retrying.
    """

    error_text = str(error).lower()

    retryable_patterns = [
        "503",
        "unavailable",
        "high demand",
        "temporarily",
        "timeout",
        "timed out",
        "429",
        "rate limit",
        "resource exhausted",
        "500",
        "internal server error",
    ]

    return any(pattern in error_text for pattern in retryable_patterns)


def generate_verdict(claim: str, evidence_chunks: list[str]) -> dict:
    """
    Generates a verdict using Google Gemini.

    Graceful degradation:
    - Retries temporary Gemini failures.
    - Does NOT convert an API failure into a claim verdict.
    - Returns a degraded verification state if Gemini remains unavailable.
    """

    api_key = os.environ.get("GEMINI_API_KEY")

    # ---------------------------------------------------------
    # 1. API KEY CHECK
    # ---------------------------------------------------------

    if not api_key:
        return {
            "verdict": None,
            "explanation": (
                "AI verification is temporarily unavailable because "
                "the Gemini API configuration is missing."
            ),
            "verification_status": "degraded",
            "ai_available": False,
            "degradation_reason": "missing_api_key",
        }

    # ---------------------------------------------------------
    # 2. CREATE GEMINI CLIENT
    # ---------------------------------------------------------

    client = genai.Client(api_key=api_key)

    evidence_text = "\n\n---\n\n".join(evidence_chunks)

    current_date = datetime.now().strftime("%B %Y")

    prompt = f"""
You are an expert fact-checker.

The current date is {current_date}.

Evaluate the following claim using ONLY the provided evidence.

Claim:
{claim}

Evidence:
{evidence_text}

Based on the evidence, classify the claim into exactly one
of these categories:

TRUE
FALSE
MISLEADING
UNVERIFIABLE

Provide your response in exactly this format:

VERDICT: [Your classification]
EXPLANATION: [A brief explanation of why, referencing the evidence]
"""

    # ---------------------------------------------------------
    # 3. GEMINI REQUEST WITH RETRIES
    # ---------------------------------------------------------

    max_retries = 3
    text = None
    last_error = None

    for attempt in range(max_retries):

        try:

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )

            text = response.text

            # Successful response
            break

        except Exception as e:

            last_error = e

            print(
                f"Gemini error on attempt "
                f"{attempt + 1}/{max_retries}: {e}"
            )

            # Only retry temporary errors
            if is_retryable_error(e) and attempt < max_retries - 1:

                wait_time = 2 ** attempt

                print(
                    f"Retrying Gemini request in "
                    f"{wait_time} seconds..."
                )

                time.sleep(wait_time)
                continue

            # Non-retryable error or final retry failed
            break

    # ---------------------------------------------------------
    # 4. GRACEFUL DEGRADATION
    # ---------------------------------------------------------

    if text is None:

        print(
            "Gemini verification unavailable after retries:",
            last_error
        )

        return {
            "verdict": None,

            "explanation": (
                "The AI verification service is temporarily "
                "unavailable. NewsCloud successfully collected "
                "supporting evidence, but a complete AI-generated "
                "verdict could not be produced."
            ),

            "verification_status": "degraded",

            "ai_available": False,

            "degradation_reason": "ai_service_unavailable",
        }

    # ---------------------------------------------------------
    # 5. PARSE GEMINI RESPONSE
    # ---------------------------------------------------------

    verdict = "UNVERIFIABLE"
    explanation = text

    for line in text.split("\n"):

        clean_line = line.replace("*", "").strip()

        if clean_line.startswith("VERDICT:"):

            verdict_str = (
                clean_line
                .replace("VERDICT:", "")
                .strip()
                .upper()
            )

            if verdict_str == "TRUE":
                verdict = "TRUE"

            elif verdict_str == "FALSE":
                verdict = "FALSE"

            elif verdict_str == "MISLEADING":
                verdict = "MISLEADING"

            elif verdict_str == "UNVERIFIABLE":
                verdict = "UNVERIFIABLE"

        elif clean_line.startswith("EXPLANATION:"):

            explanation = (
                clean_line
                .replace("EXPLANATION:", "")
                .strip()
            )

            break

    # Handle multiline explanation
    if "EXPLANATION:" in text:

        explanation = (
            text
            .replace("*", "")
            .split("EXPLANATION:", 1)[1]
            .strip()
        )

    # ---------------------------------------------------------
    # 6. NORMAL SUCCESS RESPONSE
    # ---------------------------------------------------------

    return {
        "verdict": verdict,
        "explanation": explanation,

        "verification_status": "normal",

        "ai_available": True,

        "degradation_reason": None,
    }
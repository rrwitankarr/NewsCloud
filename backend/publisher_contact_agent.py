import os
import re
import json
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
import requests
import trafilatura
from bs4 import BeautifulSoup
from ddgs import DDGS


load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

REQUEST_TIMEOUT = 15
SEARCH_RESULTS_PER_QUERY = 5


# ============================================================
# LOCALHOST / DEMO PUBLISHER CONFIGURATION
# ============================================================

# For the NewsCloud demonstration website.
# Replace this with an email address you control, or set
# NEWSCLOUD_DEMO_EMAIL in backend/.env.
DEMO_PUBLISHER_NAME = "NewsCloud Demo News"
DEMO_CONTACT_EMAIL = os.getenv(
    "NEWSCLOUD_DEMO_EMAIL",
    "demo@example.com"
)
DEMO_CONTACT_PHONE = None


# ============================================================
# BASIC URL UTILITIES
# ============================================================

def normalize_domain(url: str) -> str:
    """Return the hostname without www."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().split(":")[0]

        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    except Exception:
        return ""


def get_domain_parts(domain: str) -> list[str]:
    """
    Return useful domain components.

    Example:
        apnews.com -> ["apnews", "com"]
    """
    return [part for part in domain.split(".") if part]


# ============================================================
# PUBLISHER NAME FROM DOMAIN
# ============================================================

KNOWN_PUBLISHERS = {
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "apnews.com": "Associated Press",
    "ap.org": "Associated Press",
    "reuters.com": "Reuters",
    "cnn.com": "CNN",
    "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post",
    "theguardian.com": "The Guardian",
    "guardian.com": "The Guardian",
    "aljazeera.com": "Al Jazeera",
    "npr.org": "NPR",
    "foxnews.com": "Fox News",
    "nbcnews.com": "NBC News",
    "cbsnews.com": "CBS News",
    "abcnews.go.com": "ABC News",
    "abcnews.com": "ABC News",
    "ndtv.com": "NDTV",
    "indiatoday.in": "India Today",
    "hindustantimes.com": "Hindustan Times",
    "thehindu.com": "The Hindu",
    "indianexpress.com": "The Indian Express",
    "timesofindia.indiatimes.com": "The Times of India",
    "economictimes.indiatimes.com": "The Economic Times",
    "news18.com": "News18",
    "firstpost.com": "Firstpost",
    "deccanherald.com": "Deccan Herald",
    "livemint.com": "Mint",
    "scroll.in": "Scroll.in",
    "theprint.in": "ThePrint",
    "newindianexpress.com": "The New Indian Express",
}


def publisher_from_domain(domain: str) -> str:
    """
    Determine a readable publisher/site name from the article domain.
    Uses a small known-site map first and otherwise falls back to
    the domain's main label.
    """

    domain = domain.lower().strip()

    if domain in KNOWN_PUBLISHERS:
        return KNOWN_PUBLISHERS[domain]

    parts = get_domain_parts(domain)

    if not parts:
        return ""

    # Remove common subdomains.
    ignored = {
        "www", "news", "www2", "edition", "amp", "m"
    }

    useful = [
        part for part in parts[:-1]
        if part not in ignored
    ]

    if not useful:
        useful = parts[:-1]

    if not useful:
        return domain

    name = useful[-1]

    # Convert common separators to spaces.
    name = re.sub(r"[-_]+", " ", name)

    return name.title()


# ============================================================
# WEBPAGE SCRAPER
# ============================================================

def fetch_page(url: str) -> dict:
    """Fetch a webpage and extract title/text."""

    result = {
        "url": url,
        "title": "",
        "text": "",
        "html": "",
        "error": None,
    }

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        html = response.text
        result["html"] = html

        soup = BeautifulSoup(html, "html.parser")

        if soup.title:
            result["title"] = soup.title.get_text(
                " ",
                strip=True,
            )

        extracted = trafilatura.extract(
            html,
            include_links=True,
            include_tables=True,
        )

        if extracted:
            result["text"] = extracted
        else:
            result["text"] = soup.get_text(
                separator=" ",
                strip=True,
            )

    except Exception as e:
        result["error"] = str(e)

    return result


# ============================================================
# EMAIL EXTRACTION
# ============================================================

def extract_emails(text: str) -> list[str]:
    """Extract email addresses from text."""

    if not text:
        return []

    pattern = r"""
        [A-Za-z0-9._%+-]+
        @
        [A-Za-z0-9.-]+\.[A-Za-z]{2,}
    """

    emails = re.findall(
        pattern,
        text,
        re.VERBOSE,
    )

    unique = []

    for email in emails:
        email = email.lower().strip()

        if email not in unique:
            unique.append(email)

    return unique


# ============================================================
# PHONE EXTRACTION
# ============================================================

def extract_phone_numbers(text: str) -> list[str]:
    """Extract possible phone numbers."""

    if not text:
        return []

    patterns = [
        r"\+\d{1,3}[\s.-]?\d{3,5}[\s.-]?\d{3,5}[\s.-]?\d{3,5}",
        r"\b[6-9]\d{9}\b",
        r"\b\d{3,5}[\s.-]\d{3,5}[\s.-]\d{3,5}\b",
    ]

    numbers = []

    for pattern in patterns:

        matches = re.findall(pattern, text)

        for number in matches:

            number = number.strip()

            if number not in numbers:
                numbers.append(number)

    return numbers


# ============================================================
# SEARCH QUERY CREATION
# ============================================================

def build_search_queries(publisher: str, domain: str) -> list[str]:
    """
    Build searches that imitate the type of Google searches a person
    would make when looking for a publisher's verification/contact
    information.
    """

    queries = [
        f'"{publisher}" verification email',
        f'"{publisher}" verification contact',
        f'"{publisher}" verification team email',
        f'"{publisher}" fact check email',
        f'"{publisher}" fact checking email',
        f'"{publisher}" misinformation email',
        f'"{publisher}" misinformation contact',
        f'"{publisher}" correction email',
        f'"{publisher}" corrections email',
        f'"{publisher}" complaints email',
        f'"{publisher}" complaint contact',
        f'"{publisher}" editorial complaints',
        f'"{publisher}" grievance officer',
        f'"{publisher}" grievance email',
        f'"{publisher}" contact email',
    ]

    if domain:
        queries.extend([
            f'"{publisher}" "{domain}" email',
            f'"{publisher}" "@{domain}"',
            f'site:{domain} verification',
            f'site:{domain} fact check',
            f'site:{domain} misinformation',
            f'site:{domain} correction',
            f'site:{domain} complaints',
            f'site:{domain} contact',
        ])

    return queries


# ============================================================
# SEARCH THE WEB
# ============================================================

def search_web(publisher: str, domain: str) -> list[dict]:
    """
    Search the web through DDGS.

    Important:
    - No Gemini Search grounding is used.
    - The search result source does NOT have to be the publisher's
      own website.
    - A third-party page may contain a useful publisher email.
    """

    queries = build_search_queries(
        publisher,
        domain,
    )

    search_results = []

    print("\nSearching the web...")

    try:

        with DDGS() as ddgs:

            for query in queries:

                print(f"\n  Query: {query}")

                try:

                    results = ddgs.text(
                        query,
                        region="in-en",
                        max_results=SEARCH_RESULTS_PER_QUERY,
                        backend="auto",
                    )

                    if not results:
                        print("    No results.")
                        continue

                    for result in results:

                        title = result.get("title") or ""
                        url = result.get("href") or ""
                        snippet = result.get("body") or ""

                        print(f"    Title: {title}")
                        print(f"    URL: {url}")
                        print(f"    Snippet: {snippet}")

                        search_results.append({
                            "query": query,
                            "title": title,
                            "url": url,
                            "snippet": snippet,
                        })

                except Exception as e:
                    print(f"    Search failed: {e}")

    except Exception as e:

        print(f"\nDDGS initialization/search failed: {e}")

    return search_results


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def unique_search_results(search_results: list[dict]) -> list[dict]:
    """Remove duplicate search results by URL."""

    unique_results = []
    seen_urls = set()

    for result in search_results:

        url = result.get("url", "").strip()

        if not url:
            continue

        normalized = url.rstrip("/")

        if normalized in seen_urls:
            continue

        seen_urls.add(normalized)
        unique_results.append(result)

    return unique_results


# ============================================================
# CONTACT CANDIDATE EXTRACTION
# ============================================================

def extract_candidates_from_search_results(
    search_results: list[dict],
) -> list[dict]:
    """
    Extract emails/phones directly from search-result title/snippet.
    """

    candidates = []

    for result in search_results:

        combined_text = (
            result.get("title", "")
            + " "
            + result.get("snippet", "")
        )

        emails = extract_emails(combined_text)
        phones = extract_phone_numbers(combined_text)

        for email in emails:

            candidates.append({
                "email": email,
                "phone": phones[0] if phones else None,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("snippet", ""),
                "query": result.get("query", ""),
                "source": "search_result",
            })

    return candidates


# ============================================================
# FETCH PROMISING SEARCH RESULT PAGES
# ============================================================

def extract_candidates_from_pages(
    search_results: list[dict],
) -> list[dict]:
    """
    Open returned pages and look for emails/phone numbers.

    This is intentionally allowed to inspect third-party pages:
    the page is only the place where we discovered the contact.
    """

    candidates = []

    for index, result in enumerate(search_results):

        url = result.get("url", "")

        if not url:
            continue

        print(
            f"\n  Inspecting result page "
            f"{index + 1}/{len(search_results)}: {url}"
        )

        try:

            page = fetch_page(url)

            page_text = page.get("text", "")

            if not page_text:
                continue

            emails = extract_emails(page_text)
            phones = extract_phone_numbers(page_text)

            for email in emails:

                candidates.append({
                    "email": email,
                    "phone": phones[0] if phones else None,
                    "title": result.get("title", ""),
                    "url": url,
                    "snippet": result.get("snippet", ""),
                    "query": result.get("query", ""),
                    "source": "page",
                })

        except Exception:
            continue

    return candidates


# ============================================================
# CONTACT SCORING
# ============================================================

def score_candidate(
    candidate: dict,
    publisher: str,
    article_domain: str,
) -> int:
    """
    Rank a contact using transparent Python rules.

    The source page does NOT have to be the publisher's domain.

    A publisher-owned email domain is strong evidence, but a useful
    email discovered on a third-party page is still allowed.
    """

    email = candidate.get("email", "").lower()
    source_url = candidate.get("url", "")
    source_domain = normalize_domain(source_url)

    text = (
        candidate.get("title", "")
        + " "
        + candidate.get("snippet", "")
        + " "
        + candidate.get("query", "")
    ).lower()

    score = 0

    # ---------------------------------------------------------
    # Email naming
    # ---------------------------------------------------------

    if "grievance" in email:
        score += 12

    if "complaint" in email:
        score += 10

    if "correction" in email:
        score += 10

    if "fact" in email:
        score += 9

    if "verify" in email or "verification" in email:
        score += 9

    if "editor" in email or "editorial" in email:
        score += 8

    if "misinformation" in email:
        score += 8

    if "press" in email:
        score += 5

    if "media" in email:
        score += 5

    if "contact" in email:
        score += 3

    if "info" in email:
        score += 2

    # ---------------------------------------------------------
    # Search context
    # ---------------------------------------------------------

    keyword_weights = {
        "grievance": 6,
        "complaint": 5,
        "complaints": 5,
        "correction": 5,
        "corrections": 5,
        "fact check": 5,
        "fact-check": 5,
        "verification": 5,
        "verify": 4,
        "misinformation": 5,
        "editorial": 4,
        "contact": 2,
    }

    for keyword, weight in keyword_weights.items():

        if keyword in text:
            score += weight

    # ---------------------------------------------------------
    # Publisher/domain evidence
    # ---------------------------------------------------------

    email_domain = email.split("@")[-1]

    if article_domain and email_domain == article_domain:
        score += 12

    # Special case: an organization may use a different domain
    # from the article website. AP News is a common example:
    # apnews.com articles can use ap.org contacts.
    if article_domain == "apnews.com" and email_domain == "ap.org":
        score += 15

    # If the publisher name appears in the source result,
    # that is useful evidence even when the source is third-party.
    publisher_tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", publisher)
        if len(token) >= 3
    ]

    for token in publisher_tokens:

        if token in text:
            score += 3

    # A source on the article's own domain is useful evidence,
    # but is NOT required.
    if article_domain and source_domain == article_domain:
        score += 5

    return score


# ============================================================
# SELECT BEST CONTACT
# ============================================================

def select_best_contact(
    candidates: list[dict],
    publisher: str,
    article_domain: str,
) -> dict | None:
    """Rank candidates and return the strongest candidate."""

    if not candidates:
        return None

    # Remove duplicate email/source combinations.
    unique = []
    seen = set()

    for candidate in candidates:

        email = candidate.get("email", "").lower()
        url = candidate.get("url", "")

        key = (
            email,
            url.rstrip("/"),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(candidate)

    for candidate in unique:

        candidate["score"] = score_candidate(
            candidate,
            publisher,
            article_domain,
        )

    unique.sort(
        key=lambda item: item.get("score", 0),
        reverse=True,
    )

    print("\n" + "=" * 70)
    print("CONTACT CANDIDATES RANKED BY PYTHON")
    print("=" * 70)

    for candidate in unique[:15]:

        print(
            f"\nScore: {candidate['score']}"
            f"\nEmail: {candidate['email']}"
            f"\nPhone: {candidate.get('phone')}"
            f"\nSource: {candidate['url']}"
            f"\nQuery: {candidate['query']}"
        )

    return unique[0]


# ============================================================
# DETERMINE CONTACT TYPE
# ============================================================

def determine_contact_type(candidate: dict) -> str:

    text = (
        candidate.get("title", "")
        + " "
        + candidate.get("snippet", "")
        + " "
        + candidate.get("query", "")
        + " "
        + candidate.get("email", "")
    ).lower()

    if "grievance" in text:
        return "grievance_redressal"

    if "complaint" in text:
        return "complaints"

    if "correction" in text:
        return "corrections"

    if "fact check" in text or "fact-check" in text:
        return "fact_check"

    if "verification" in text or "verify" in text:
        return "verification"

    if "editorial" in text:
        return "editorial_complaints"

    if "media" in text or "press" in text:
        return "media_contact"

    return "official_contact"


# ============================================================
# DETERMINE CONFIDENCE
# ============================================================

def determine_confidence(
    candidate: dict,
    article_domain: str,
) -> str:

    score = candidate.get("score", 0)
    email = candidate.get("email", "").lower()
    email_domain = email.split("@")[-1]
    source_domain = normalize_domain(
        candidate.get("url", "")
    )

    domain_match = (
        article_domain
        and email_domain == article_domain
    )

    known_ap_match = (
        article_domain == "apnews.com"
        and email_domain == "ap.org"
    )

    publisher_context = (
        "associated press" in (
            candidate.get("title", "").lower()
            + " "
            + candidate.get("snippet", "").lower()
        )
    )

    if score >= 25 or domain_match or known_ap_match:
        return "high"

    if score >= 15 or publisher_context:
        return "medium"

    return "low"


# ============================================================
# LOCALHOST / DEMO CONTROLLER
# ============================================================

def is_localhost_url(article_url: str) -> bool:
    """Return True when the article URL points to localhost."""

    try:
        parsed = urlparse(article_url)
        hostname = (parsed.hostname or "").lower()

        return hostname in {
            "localhost",
            "127.0.0.1",
        }

    except Exception:
        return False


def publisher_contact_agent_demo(article_url: str) -> dict:
    """
    Controlled publisher/contact result for the NewsCloud demo article.

    This keeps the real Publisher Agent unchanged for real news domains.
    The returned structure intentionally matches the normal agent output
    so downstream complaint/email code can consume it normally.
    """

    print("\n" + "=" * 70)
    print("PUBLISHER CONTACT AGENT - LOCALHOST DEMO MODE")
    print("=" * 70)

    print(f"\nArticle URL:\n{article_url}")

    print("\n[DEMO] Scraping local test article...")

    article = fetch_page(article_url)

    if article["error"]:
        print("\n[DEMO] Local article access failed.")
        print("Error:", article["error"])

        return {
            "success": False,
            "stage": "article_scraping",
            "error": article["error"],
            "article": {
                "url": article_url,
                "title": "",
            },
        }

    print(f"Article title: {article['title']}")

    publisher_info = {
        "website_name": DEMO_PUBLISHER_NAME,
        "publisher_name": DEMO_PUBLISHER_NAME,
        "author": "",
        "visible_contact": DEMO_CONTACT_EMAIL,
        "official_domain": "localhost",
    }

    contact = {
        "publisher_name": DEMO_PUBLISHER_NAME,
        "contact_name": None,
        "contact_email": DEMO_CONTACT_EMAIL,
        "contact_phone": DEMO_CONTACT_PHONE,
        "contact_type": "complaints",
        "complaint_form_url": None,
        "contact_source_url": article_url,
        "official_domain_verified": True,
        "search_performed": False,
        "official_source_found": True,
        "reason": (
            "Controlled NewsCloud demonstration publisher. "
            "The localhost domain is intentionally mapped to a "
            "test publisher/contact so the complete complaint workflow "
            "can be demonstrated without relying on real misinformation."
        ),
        "confidence": "high",
    }

    result = {
        "success": True,
        "demo_mode": True,
        "article": {
            "url": article_url,
            "title": article["title"],
        },
        "publisher": publisher_info,
        "contact": contact,
    }

    print("\n[DEMO] Publisher:", DEMO_PUBLISHER_NAME)
    print("[DEMO] Contact email:", DEMO_CONTACT_EMAIL)
    print("[DEMO] Web search skipped.")
    print("[DEMO] Controlled publisher contact returned.")

    print("\n" + "=" * 70)
    print("DEMO FINAL RESULT")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )

    return result


# ============================================================
# MAIN CONTACT AGENT
# ============================================================

def publisher_contact_agent(article_url: str) -> dict:

    # --------------------------------------------------------
    # LOCALHOST DEMO CONTROLLER
    # --------------------------------------------------------
    # Real-world publisher extraction remains unchanged.
    # Only localhost / 127.0.0.1 enters the controlled demo path.

    if is_localhost_url(article_url):
        return publisher_contact_agent_demo(article_url)

    print("\n" + "=" * 70)
    print("PUBLISHER CONTACT AGENT")
    print("=" * 70)

    print(f"\nArticle URL:\n{article_url}")

    # --------------------------------------------------------
    # STEP 1: Scrape article
    # --------------------------------------------------------

    print("\n[1] Scraping article...")

    article = fetch_page(article_url)

    if article["error"]:

        print("\n⚠️ DIRECT ARTICLE ACCESS FAILED")
        print("Error:", article["error"])
        print("Continuing using the article URL/domain...")

        article["text"] = ""
        article["title"] = ""

    print(
        f"Article title: {article['title']}"
    )

    # --------------------------------------------------------
    # STEP 2: Determine publisher/domain using Python
    # --------------------------------------------------------

    print("\n[2] Identifying publisher using Python...")

    article_domain = normalize_domain(article_url)

    publisher = publisher_from_domain(
        article_domain
    )

    if not publisher:

        return {
            "success": False,
            "stage": "publisher_identification",
            "error": "Could not determine publisher from article domain.",
            "article": {
                "url": article_url,
                "title": article["title"],
            },
        }

    publisher_info = {
        "website_name": publisher,
        "publisher_name": publisher,
        "author": "",
        "visible_contact": "",
        "official_domain": article_domain,
    }

    print("\nPublisher information:")
    print(
        json.dumps(
            publisher_info,
            indent=2,
            ensure_ascii=False,
        )
    )

    print(
        f"\nArticle domain: {article_domain}"
    )

    # --------------------------------------------------------
    # STEP 3: Search web
    # --------------------------------------------------------

    print(
        "\n[3] Searching web for publisher contact..."
    )

    search_results = search_web(
        publisher,
        article_domain,
    )

    unique_results = unique_search_results(
        search_results
    )

    print(
        f"\nCollected {len(unique_results)} unique search results."
    )

    # --------------------------------------------------------
    # STEP 4: Extract directly from snippets
    # --------------------------------------------------------

    print(
        "\n[4] Extracting contact information from search results..."
    )

    snippet_candidates = (
        extract_candidates_from_search_results(
            unique_results
        )
    )

    # --------------------------------------------------------
    # STEP 5: Inspect result pages
    # --------------------------------------------------------

    print(
        "\n[5] Inspecting returned pages for additional contacts..."
    )

    page_candidates = (
        extract_candidates_from_pages(
            unique_results
        )
    )

    all_candidates = (
        snippet_candidates
        + page_candidates
    )

    # --------------------------------------------------------
    # STEP 6: Select best contact
    # --------------------------------------------------------

    print(
        "\n[6] Selecting best contact using Python..."
    )

    best = select_best_contact(
        all_candidates,
        publisher,
        article_domain,
    )

    if not best:

        contact = {
            "publisher_name": publisher,
            "contact_name": None,
            "contact_email": None,
            "contact_phone": None,
            "contact_type": "unavailable",
            "complaint_form_url": None,
            "contact_source_url": None,
            "official_domain_verified": False,
            "search_performed": True,
            "official_source_found": False,
            "reason": (
                "Web search completed, but no email or phone "
                "number could be extracted from the returned "
                "results/pages."
            ),
            "confidence": "low",
        }

    else:

        email = best.get("email", "").lower()
        email_domain = email.split("@")[-1]

        official_email_domain = (
            email_domain == article_domain
        )

        # AP is a deliberate example where the article domain
        # and organization email domain differ.
        if (
            article_domain == "apnews.com"
            and email_domain == "ap.org"
        ):
            official_email_domain = True

        contact = {
            "publisher_name": publisher,
            "contact_name": None,
            "contact_email": best.get("email"),
            "contact_phone": best.get("phone"),
            "contact_type": determine_contact_type(best),
            "complaint_form_url": None,
            "contact_source_url": best.get("url"),
            "official_domain_verified": official_email_domain,
            "search_performed": True,
            "official_source_found": official_email_domain,
            "reason": (
                "Contact information was discovered through web "
                "search and extracted/ranked directly by Python. "
                "The source page does not have to be the publisher's "
                "own website."
            ),
            "confidence": determine_confidence(
                best,
                article_domain,
            ),
        }

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    result = {
        "success": True,
        "article": {
            "url": article_url,
            "title": article["title"],
        },
        "publisher": publisher_info,
        "contact": contact,
    }

    print("\n" + "=" * 70)
    print("FINAL RESULT")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )

    return result


# ============================================================
# COMMAND LINE TEST
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) >= 2:
        url = sys.argv[1]
    else:
        url = input(
            "\nEnter news article URL: "
        ).strip()

    if not url:
        print("No URL provided.")
        sys.exit(1)

    publisher_contact_agent(url)

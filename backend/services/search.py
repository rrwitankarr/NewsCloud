import time
from ddgs import DDGS

def search_web_for_claim(claim: str, max_results: int = 5) -> dict:
    """
    Search DuckDuckGo for the given claim and return URLs and snippets.
    Includes basic retry logic for rate limiting.
    """
    urls = []
    snippets = []
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(claim, max_results=max_results))
                if results:
                    urls = [r.get("href") for r in results if r.get("href")]
                    snippets = [r.get("body") for r in results if r.get("body")]
                    break
        except Exception as e:
            print(f"Search attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                
    return {"urls": urls, "snippets": snippets}

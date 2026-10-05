import trafilatura
from bs4 import BeautifulSoup

def scrape_url(url: str) -> str:
    """
    Scrape the main body text from a given URL using Trafilatura.
    Falls back to basic BeautifulSoup if Trafilatura fails.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text:
                return text
        
        # Fallback (very basic)
        import requests
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.content, "html.parser")
        return soup.get_text(separator=' ', strip=True)
    except Exception as e:
        print(f"Failed to scrape {url}: {e}")
        return ""

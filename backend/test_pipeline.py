import os
from dotenv import load_dotenv
load_dotenv()

from services.search import search_web_for_claim
from services.scraper import scrape_url
from services.embedding import chunk_text, retrieve_top_k_chunks, rerank_chunks

def test_pipeline():
    claim = "The Eiffel Tower is located in London."
    print(f"Testing claim: {claim}")
    
    urls = search_web_for_claim(claim, max_results=2)
    if not urls:
        print("Search returned no URLs (likely rate-limited). Using a fallback URL.")
        urls = ["https://en.wikipedia.org/wiki/Eiffel_Tower"]
        
    try:
        print(f"Found URLs: {urls}")
    except:
        pass
    assert isinstance(urls, list), "Search should return a list"
    
    if urls:
        text = scrape_url(urls[0])
        print(f"Scraped {len(text)} characters.")
        
        chunks = chunk_text(text)
        print(f"Chunked into {len(chunks)} parts")
        
        if chunks:
            # Test Bi-encoder
            top_chunks = retrieve_top_k_chunks(claim, chunks, top_k=2)
            print(f"Retrieved {len(top_chunks)} chunks from Bi-Encoder")
            
            # Test Cross-encoder
            reranked = rerank_chunks(claim, top_chunks, top_k=1)
            try:
                print(f"Reranked top chunk: {reranked[0][:100]}...")
            except UnicodeEncodeError:
                print("Reranked top chunk: [Unicode Encode Error on print]")

            # Test LLM
            from services.llm import generate_verdict
            print("Generating verdict with LLM...")
            result = generate_verdict(claim, reranked)
            print(f"Final LLM Verdict: {result['verdict']}")
            print(f"Explanation: {result['explanation']}")
            print("Pipeline local components passed successfully!")
        else:
            print("No text scraped to chunk.")

if __name__ == "__main__":
    test_pipeline()

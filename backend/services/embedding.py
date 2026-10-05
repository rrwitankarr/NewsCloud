from sentence_transformers import SentenceTransformer, CrossEncoder
from langchain_text_splitters import RecursiveCharacterTextSplitter
import torch

# Initialize models lazily or globally
_bi_encoder = None
_cross_encoder = None

def get_bi_encoder():
    global _bi_encoder
    if _bi_encoder is None:
        _bi_encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _bi_encoder

def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder

def chunk_text(text: str, chunk_size: int = 400, chunk_overlap: int = 50) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    return splitter.split_text(text)

def retrieve_top_k_chunks(claim: str, chunks: list[str], top_k: int = 50) -> list[str]:
    if not chunks:
        return []
    
    bi_encoder = get_bi_encoder()
    claim_embedding = bi_encoder.encode(claim, convert_to_tensor=True)
    chunk_embeddings = bi_encoder.encode(chunks, convert_to_tensor=True)
    
    from sentence_transformers import util
    cos_scores = util.cos_sim(claim_embedding, chunk_embeddings)[0]
    
    # Get top_k
    top_results = torch.topk(cos_scores, k=min(top_k, len(chunks)))
    
    return [chunks[i] for i in top_results[1]]

def rerank_chunks(claim: str, chunks: list[str], top_k: int = 5) -> list[str]:
    if not chunks:
        return []
    
    cross_encoder = get_cross_encoder()
    
    # Pair claim with each chunk
    pairs = [[claim, chunk] for chunk in chunks]
    scores = cross_encoder.predict(pairs)
    
    # Sort chunks by score
    scored_chunks = list(zip(scores, chunks))
    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    
    # Return top_k chunks
    return [chunk for score, chunk in scored_chunks[:top_k]]

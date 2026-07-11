import os
import re
import math
from collections import Counter
from typing import List, Dict, Any
from ..config import settings

# Attempt to import chromadb
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    print("chromadb not installed or failed to import. Using native fallback vector store.")

# Word-level tokenizer: lowercase alphanumeric runs. Shared so indexing and
# querying tokenize identically.
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


class FallbackVectorStore:
    """
    A lightweight, dependency-free vector store used when ChromaDB is
    unavailable.

    Each meeting's transcript is chunked, and every chunk is represented as a
    TF-IDF vector (smoothed IDF, L2-normalized). Queries are ranked by cosine
    similarity, which captures term importance far better than the previous
    plain Jaccard word-overlap heuristic (rare, discriminative words dominate
    over common filler words).
    """
    def __init__(self):
        # meeting_id -> {"chunks": [...], "vectors": [ {term: weight} ], "idf": {term: idf}}
        self.documents: Dict[int, Dict[str, Any]] = {}

    def add_transcript(self, meeting_id: int, transcript: str):
        chunks = self._chunk_text(transcript)
        self.documents[meeting_id] = self._build_index(chunks)

    def query_transcript(self, meeting_id: int, query: str, limit: int = 3) -> List[str]:
        doc = self.documents.get(meeting_id)
        if not doc or not doc["chunks"]:
            return []

        query_vec = self._embed(_tokenize(query), doc["idf"])
        chunks = doc["chunks"]
        vectors = doc["vectors"]

        # Cosine similarity == dot product of L2-normalized vectors.
        scored = [
            (self._cosine(query_vec, vectors[i]), i)
            for i in range(len(chunks))
        ]
        scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)

        # If nothing overlaps the query, fall back to the leading chunks so the
        # chat still receives some context rather than nothing.
        if scored and scored[0][0] == 0.0:
            return chunks[:limit]
        return [chunks[i] for _, i in scored[:limit]]

    def delete_transcript(self, meeting_id: int):
        if meeting_id in self.documents:
            del self.documents[meeting_id]

    # ------------------- TF-IDF internals -------------------

    def _build_index(self, chunks: List[str]) -> Dict[str, Any]:
        tokenized = [_tokenize(c) for c in chunks]
        n_docs = len(chunks)

        # Document frequency: number of chunks each term appears in.
        df: Counter = Counter()
        for tokens in tokenized:
            for term in set(tokens):
                df[term] += 1

        # Smoothed IDF (sklearn-style): log((1 + N) / (1 + df)) + 1. Always
        # positive, so single-chunk documents still yield usable vectors.
        idf = {
            term: math.log((1 + n_docs) / (1 + freq)) + 1.0
            for term, freq in df.items()
        }

        vectors = [self._embed(tokens, idf) for tokens in tokenized]
        return {"chunks": chunks, "vectors": vectors, "idf": idf}

    def _embed(self, tokens: List[str], idf: Dict[str, float]) -> Dict[str, float]:
        """Build an L2-normalized TF-IDF vector for a token list. Terms absent
        from ``idf`` (unseen at index time) contribute nothing to similarity and
        are dropped."""
        if not tokens:
            return {}
        tf = Counter(tokens)
        vec = {
            term: count * idf[term]
            for term, count in tf.items()
            if term in idf
        }
        norm = math.sqrt(sum(w * w for w in vec.values()))
        if norm == 0.0:
            return {}
        return {term: w / norm for term, w in vec.items()}

    @staticmethod
    def _cosine(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        # Both vectors are already L2-normalized, so the dot product is cosine.
        # Iterate over the smaller vector for efficiency.
        if len(vec_a) > len(vec_b):
            vec_a, vec_b = vec_b, vec_a
        return sum(w * vec_b.get(term, 0.0) for term, w in vec_a.items())

    def _chunk_text(self, text: str, chunk_size: int = 150, overlap: int = 30) -> List[str]:
        words = text.split()
        chunks = []
        if len(words) <= chunk_size:
            return [text]

        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += (chunk_size - overlap)
        return chunks


class VectorService:
    def __init__(self):
        self.chroma_client = None
        self.fallback_store = FallbackVectorStore()
        
        if HAS_CHROMADB:
            try:
                # Persistent client
                self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
            except Exception as e:
                print(f"Error initializing ChromaDB client: {e}. Falling back.")
                self.chroma_client = None

    def index_meeting(self, meeting_id: int, transcript: str):
        """
        Chunks the transcript and stores in ChromaDB or fallback store.
        """
        if not transcript:
            return

        if self.chroma_client:
            try:
                collection_name = f"meeting_{meeting_id}"
                # Delete existing if it exists
                try:
                    self.chroma_client.delete_collection(name=collection_name)
                except Exception:
                    pass
                
                collection = self.chroma_client.create_collection(name=collection_name)
                chunks = self.fallback_store._chunk_text(transcript)
                
                ids = [f"chunk_{i}" for i in range(len(chunks))]
                # ChromaDB can generate standard embeddings automatically or we can provide text
                collection.add(
                    documents=chunks,
                    ids=ids
                )
                return
            except Exception as e:
                print(f"ChromaDB index failed: {e}. Falling back.")

        # Fallback
        self.fallback_store.add_transcript(meeting_id, transcript)

    def query_meeting(self, meeting_id: int, query: str, limit: int = 3) -> List[str]:
        """
        Queries ChromaDB or fallback store for relevant transcript chunks.
        """
        if self.chroma_client:
            try:
                collection_name = f"meeting_{meeting_id}"
                collection = self.chroma_client.get_collection(name=collection_name)
                results = collection.query(
                    query_texts=[query],
                    n_results=limit
                )
                if results and 'documents' in results and results['documents']:
                    return results['documents'][0]
            except Exception as e:
                print(f"ChromaDB query failed: {e}. Using fallback query.")

        return self.fallback_store.query_transcript(meeting_id, query, limit)

    def delete_meeting_index(self, meeting_id: int):
        """
        Deletes the vector index for a meeting.
        """
        if self.chroma_client:
            try:
                collection_name = f"meeting_{meeting_id}"
                self.chroma_client.delete_collection(name=collection_name)
            except Exception as e:
                print(f"ChromaDB delete failed: {e}")
        
        self.fallback_store.delete_transcript(meeting_id)

vector_service = VectorService()

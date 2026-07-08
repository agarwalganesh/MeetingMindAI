import os
import math
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

class FallbackVectorStore:
    """
    A lightweight, native Python SQLite/in-memory vector store fallback.
    Uses TF-IDF / overlap vector representations and cosine similarity.
    """
    def __init__(self):
        self.documents = {}  # meeting_id -> list of chunks

    def add_transcript(self, meeting_id: int, transcript: str):
        chunks = self._chunk_text(transcript)
        self.documents[meeting_id] = chunks

    def query_transcript(self, meeting_id: int, query: str, limit: int = 3) -> List[str]:
        chunks = self.documents.get(meeting_id, [])
        if not chunks:
            # Try to chunk it dynamically if not stored
            return []

        # Simple Jaccard/Overlap similarity for ranking
        query_words = set(query.lower().split())
        scored_chunks = []
        for chunk in chunks:
            chunk_words = set(chunk.lower().split())
            intersection = query_words.intersection(chunk_words)
            union = query_words.union(chunk_words)
            score = len(intersection) / len(union) if union else 0.0
            scored_chunks.append((score, chunk))

        # Sort by score descending
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [chunk for score, chunk in scored_chunks[:limit]]

    def delete_transcript(self, meeting_id: int):
        if meeting_id in self.documents:
            del self.documents[meeting_id]

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

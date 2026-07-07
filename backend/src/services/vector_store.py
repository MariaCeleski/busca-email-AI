"""ChromaDB Vector Store Service — stores and retrieves email embeddings."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import chromadb
from openai import OpenAI

from src.config import get_settings
from src.models.vector_store import EmailMetadata, MetadataFilter, SearchResult

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Manages email embeddings storage and similarity search using ChromaDB."""

    def __init__(
        self,
        collection_name: Optional[str] = None,
        persist_directory: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self._collection_name = collection_name or settings.chromadb_collection_name
        self._persist_directory = persist_directory or settings.chromadb_persist_directory
        self._embedding_model = settings.openai_embedding_model

        self._openai_client = OpenAI(api_key=settings.openai_api_key)

        self._client = chromadb.Client(
            chromadb.Settings(
                persist_directory=self._persist_directory,
                anonymized_telemetry=False,
            )
        )
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector using OpenAI embedding model."""
        result = self._openai_client.embeddings.create(
            model=self._embedding_model,
            input=text,
        )
        return result.data[0].embedding

    def _generate_query_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for a query using OpenAI embedding model."""
        return self._generate_embedding(text)

    def store_embedding(
        self, email_id: str, text: str, metadata: EmailMetadata
    ) -> str:
        """Generate embedding via Gemini and store in ChromaDB.

        Args:
            email_id: Unique identifier for the email.
            text: Email text content to embed.
            metadata: Structured metadata for the email.

        Returns:
            The record ID stored in ChromaDB.
        """
        embedding = self._generate_embedding(text)

        record_id = f"emb_{email_id}"

        # Flatten metadata for ChromaDB storage (only primitive types allowed)
        chroma_metadata: Dict[str, str] = {
            "email_id": metadata.email_id,
            "sender": metadata.sender,
            "timestamp": metadata.timestamp.isoformat(),
            "category": metadata.category.value,
            "provider_message_id": metadata.provider_message_id,
        }
        if metadata.thread_id:
            chroma_metadata["thread_id"] = metadata.thread_id

        self._collection.upsert(
            ids=[record_id],
            embeddings=[embedding],
            metadatas=[chroma_metadata],
            documents=[text],
        )

        logger.info("Stored embedding for email_id=%s as record_id=%s", email_id, record_id)
        return record_id

    def search_similar(
        self,
        query_text: str,
        k: int = 5,
        filters: Optional[MetadataFilter] = None,
    ) -> List[SearchResult]:
        """Find top-k similar emails by cosine similarity.

        Args:
            query_text: Text to find similar emails for.
            k: Number of results to return (default 5).
            filters: Optional metadata filters (sender, date_range, category).

        Returns:
            List of SearchResult sorted by similarity descending.
        """
        query_embedding = self._generate_query_embedding(query_text)

        where_filter = self._build_where_filter(filters)

        query_params: Dict = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["metadatas", "documents", "distances"],
        }
        if where_filter:
            query_params["where"] = where_filter

        results = self._collection.query(**query_params)

        return self._parse_search_results(results)

    def delete_by_user(self, user_id: str) -> int:
        """Delete all embeddings for a user (by sender field).

        Args:
            user_id: The user/sender identifier to delete embeddings for.

        Returns:
            Count of records deleted.
        """
        # Get all records matching user_id in sender metadata
        existing = self._collection.get(
            where={"sender": user_id},
            include=["metadatas"],
        )

        ids_to_delete = existing["ids"]
        if not ids_to_delete:
            return 0

        self._collection.delete(ids=ids_to_delete)
        logger.info("Deleted %d embeddings for user_id=%s", len(ids_to_delete), user_id)
        return len(ids_to_delete)

    def is_duplicate(self, email_provider_message_id: str) -> bool:
        """Check if embedding already exists for this provider message ID.

        Args:
            email_provider_message_id: The provider-specific message identifier.

        Returns:
            True if an embedding already exists for this message ID.
        """
        existing = self._collection.get(
            where={"provider_message_id": email_provider_message_id},
            include=["metadatas"],
        )
        return len(existing["ids"]) > 0

    def _build_where_filter(self, filters: Optional[MetadataFilter]) -> Optional[Dict]:
        """Build ChromaDB where filter from MetadataFilter."""
        if filters is None:
            return None

        conditions: List[Dict] = []

        if filters.sender:
            conditions.append({"sender": {"$eq": filters.sender}})

        if filters.category:
            conditions.append({"category": {"$eq": filters.category.value}})

        if filters.date_from:
            conditions.append(
                {"timestamp": {"$gte": filters.date_from.isoformat()}}
            )

        if filters.date_to:
            conditions.append(
                {"timestamp": {"$lte": filters.date_to.isoformat()}}
            )

        if not conditions:
            return None

        if len(conditions) == 1:
            return conditions[0]

        return {"$and": conditions}

    def _parse_search_results(self, results: Dict) -> List[SearchResult]:
        """Parse ChromaDB query results into SearchResult models."""
        search_results: List[SearchResult] = []

        if not results["ids"] or not results["ids"][0]:
            return search_results

        ids = results["ids"][0]
        metadatas = results["metadatas"][0]
        documents = results["documents"][0] if results.get("documents") else [None] * len(ids)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)

        for i, _record_id in enumerate(ids):
            meta = metadatas[i]
            # ChromaDB cosine distance: distance = 1 - similarity
            similarity_score = 1.0 - distances[i]

            from datetime import datetime
            from src.models.enums import EmailCategory

            email_metadata = EmailMetadata(
                email_id=meta["email_id"],
                sender=meta["sender"],
                timestamp=datetime.fromisoformat(meta["timestamp"]),
                category=EmailCategory(meta["category"]),
                provider_message_id=meta["provider_message_id"],
                thread_id=meta.get("thread_id"),
            )

            search_results.append(
                SearchResult(
                    email_id=meta["email_id"],
                    metadata=email_metadata,
                    similarity_score=similarity_score,
                    text_snippet=documents[i][:200] if documents[i] else None,
                )
            )

        # Sort by similarity descending
        search_results.sort(key=lambda r: r.similarity_score, reverse=True)
        return search_results

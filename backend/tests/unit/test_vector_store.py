"""Unit tests for VectorStoreService — store, search, delete, deduplication."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.models.enums import EmailCategory
from src.models.vector_store import EmailMetadata, MetadataFilter, SearchResult


def _make_embedding_response(vector: List[float]) -> MagicMock:
    """Build a mock OpenAI embeddings.create response object."""
    response = MagicMock()
    data_item = MagicMock()
    data_item.embedding = vector
    response.data = [data_item]
    return response


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    with patch("src.services.vector_store.get_settings") as mock:
        settings = MagicMock()
        settings.openai_api_key = "test-api-key"
        settings.openai_embedding_model = "text-embedding-3-small"
        settings.chromadb_collection_name = "test_collection"
        settings.chromadb_persist_directory = "/tmp/test_chroma"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for embeddings."""
    with patch("src.services.vector_store.OpenAI") as mock_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.embeddings = MagicMock()
        mock_client_instance.embeddings.create = MagicMock(
            return_value=_make_embedding_response([0.1] * 1536)
        )
        mock_cls.return_value = mock_client_instance
        yield mock_cls, mock_client_instance


@pytest.fixture
def mock_chromadb():
    """Mock chromadb client and collection."""
    with patch("src.services.vector_store.chromadb") as mock:
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        mock.Client.return_value = mock_client
        mock.Settings.return_value = MagicMock()

        yield mock, mock_client, mock_collection


@pytest.fixture
def vector_store(mock_settings, mock_openai, mock_chromadb):
    """Create VectorStoreService instance with mocks."""
    from src.services.vector_store import VectorStoreService

    service = VectorStoreService()
    return service


@pytest.fixture
def sample_metadata():
    """Create sample EmailMetadata."""
    return EmailMetadata(
        email_id="email-123",
        sender="sender@example.com",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        category=EmailCategory.PERSONAL,
        provider_message_id="msg-abc-123",
        thread_id="thread-1",
    )


class TestStoreEmbedding:
    """Tests for store_embedding method."""

    def test_store_embedding_returns_record_id(
        self, vector_store, mock_openai, mock_chromadb, sample_metadata
    ):
        """store_embedding should return a record ID."""
        _, _, mock_collection = mock_chromadb

        result = vector_store.store_embedding(
            email_id="email-123",
            text="Hello, this is a test email.",
            metadata=sample_metadata,
        )

        assert result == "emb_email-123"

    def test_store_embedding_calls_openai_embed(
        self, vector_store, mock_openai, mock_chromadb, sample_metadata
    ):
        """store_embedding should call OpenAI embeddings.create."""
        _, mock_client = mock_openai

        vector_store.store_embedding(
            email_id="email-123",
            text="Hello, this is a test email.",
            metadata=sample_metadata,
        )

        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input="Hello, this is a test email.",
        )

    def test_store_embedding_upserts_to_collection(
        self, vector_store, mock_openai, mock_chromadb, sample_metadata
    ):
        """store_embedding should upsert the embedding with metadata to ChromaDB."""
        _, _, mock_collection = mock_chromadb

        vector_store.store_embedding(
            email_id="email-123",
            text="Test email body",
            metadata=sample_metadata,
        )

        mock_collection.upsert.assert_called_once()
        call_kwargs = mock_collection.upsert.call_args[1]
        assert call_kwargs["ids"] == ["emb_email-123"]
        assert call_kwargs["embeddings"] == [[0.1] * 1536]
        assert call_kwargs["documents"] == ["Test email body"]
        assert call_kwargs["metadatas"][0]["email_id"] == "email-123"
        assert call_kwargs["metadatas"][0]["sender"] == "sender@example.com"
        assert call_kwargs["metadatas"][0]["category"] == "Personal"
        assert call_kwargs["metadatas"][0]["provider_message_id"] == "msg-abc-123"
        assert call_kwargs["metadatas"][0]["thread_id"] == "thread-1"

    def test_store_embedding_without_thread_id(
        self, vector_store, mock_openai, mock_chromadb
    ):
        """store_embedding should not include thread_id when it's None."""
        _, _, mock_collection = mock_chromadb
        metadata = EmailMetadata(
            email_id="email-456",
            sender="test@example.com",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            category=EmailCategory.URGENT,
            provider_message_id="msg-456",
            thread_id=None,
        )

        vector_store.store_embedding(
            email_id="email-456",
            text="Urgent email",
            metadata=metadata,
        )

        call_kwargs = mock_collection.upsert.call_args[1]
        assert "thread_id" not in call_kwargs["metadatas"][0]


class TestSearchSimilar:
    """Tests for search_similar method."""

    def test_search_similar_returns_results(
        self, vector_store, mock_openai, mock_chromadb
    ):
        """search_similar should return a list of SearchResult."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [["emb_email-1", "emb_email-2"]],
            "metadatas": [[
                {
                    "email_id": "email-1",
                    "sender": "alice@example.com",
                    "timestamp": "2024-01-15T10:00:00",
                    "category": "Personal",
                    "provider_message_id": "msg-1",
                },
                {
                    "email_id": "email-2",
                    "sender": "bob@example.com",
                    "timestamp": "2024-01-14T09:00:00",
                    "category": "Urgent",
                    "provider_message_id": "msg-2",
                },
            ]],
            "documents": [["Hello Alice email text", "Hello Bob email text"]],
            "distances": [[0.1, 0.3]],
        }

        results = vector_store.search_similar("test query", k=5)

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        # Similarity = 1 - distance, sorted descending
        assert results[0].similarity_score == pytest.approx(0.9)
        assert results[1].similarity_score == pytest.approx(0.7)
        assert results[0].email_id == "email-1"

    def test_search_similar_uses_query_embedding(
        self, vector_store, mock_openai, mock_chromadb
    ):
        """search_similar should generate a query embedding via OpenAI."""
        _, mock_client = mock_openai
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        vector_store.search_similar("test query")

        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input="test query",
        )

    def test_search_similar_empty_results(
        self, vector_store, mock_openai, mock_chromadb
    ):
        """search_similar should return empty list when no results."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        results = vector_store.search_similar("nothing here")

        assert results == []

    def test_search_similar_with_sender_filter(
        self, vector_store, mock_openai, mock_chromadb
    ):
        """search_similar should pass sender filter to ChromaDB."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        filters = MetadataFilter(sender="alice@example.com")
        vector_store.search_similar("query", filters=filters)

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"sender": {"$eq": "alice@example.com"}}

    def test_search_similar_with_category_filter(
        self, vector_store, mock_openai, mock_chromadb
    ):
        """search_similar should pass category filter to ChromaDB."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        filters = MetadataFilter(category=EmailCategory.URGENT)
        vector_store.search_similar("query", filters=filters)

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"category": {"$eq": "Urgent"}}

    def test_search_similar_with_combined_filters(
        self, vector_store, mock_openai, mock_chromadb
    ):
        """search_similar should combine multiple filters with $and."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        filters = MetadataFilter(
            sender="alice@example.com",
            category=EmailCategory.PERSONAL,
        )
        vector_store.search_similar("query", filters=filters)

        call_kwargs = mock_collection.query.call_args[1]
        assert "$and" in call_kwargs["where"]


class TestDeleteByUser:
    """Tests for delete_by_user method."""

    def test_delete_by_user_returns_count(
        self, vector_store, mock_chromadb
    ):
        """delete_by_user should return count of deleted records."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {
            "ids": ["emb_email-1", "emb_email-2", "emb_email-3"],
            "metadatas": [{}, {}, {}],
        }

        count = vector_store.delete_by_user("alice@example.com")

        assert count == 3
        mock_collection.delete.assert_called_once_with(
            ids=["emb_email-1", "emb_email-2", "emb_email-3"]
        )

    def test_delete_by_user_no_records(
        self, vector_store, mock_chromadb
    ):
        """delete_by_user should return 0 when no records found."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {
            "ids": [],
            "metadatas": [],
        }

        count = vector_store.delete_by_user("nobody@example.com")

        assert count == 0
        mock_collection.delete.assert_not_called()


class TestIsDuplicate:
    """Tests for is_duplicate method."""

    def test_is_duplicate_returns_true_when_exists(
        self, vector_store, mock_chromadb
    ):
        """is_duplicate should return True when provider_message_id exists."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {
            "ids": ["emb_email-1"],
            "metadatas": [{"provider_message_id": "msg-abc"}],
        }

        result = vector_store.is_duplicate("msg-abc")

        assert result is True

    def test_is_duplicate_returns_false_when_not_exists(
        self, vector_store, mock_chromadb
    ):
        """is_duplicate should return False when provider_message_id not found."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {
            "ids": [],
            "metadatas": [],
        }

        result = vector_store.is_duplicate("msg-nonexistent")

        assert result is False

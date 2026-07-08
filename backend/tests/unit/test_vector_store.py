"""Unit tests for VectorStoreService — store, search, delete, deduplication."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.models.enums import EmailCategory
from src.models.vector_store import EmailMetadata, MetadataFilter, SearchResult


# --- Fixtures ---


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    with patch("src.services.vector_store.get_settings") as mock:
        settings = MagicMock()
        settings.gemini_api_key = "test-gemini-key"
        settings.gemini_embedding_model = "gemini-embedding-001"
        settings.chromadb_collection_name = "test_collection"
        settings.chromadb_persist_directory = "/tmp/test_chroma"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_genai():
    """Mock google.generativeai for embeddings."""
    with patch("src.services.vector_store.genai") as mock:
        # Mock embed_content to return a 3072-dim vector
        mock.embed_content.return_value = {"embedding": [0.1] * 3072}
        yield mock


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
def vector_store(mock_settings, mock_genai, mock_chromadb):
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
        user_id="user-001",
    )


# --- Tests for store_embedding ---


class TestStoreEmbedding:
    """Tests for store_embedding method."""

    @pytest.mark.asyncio
    async def test_store_embedding_returns_record_id(
        self, vector_store, mock_genai, mock_chromadb, sample_metadata
    ):
        """store_embedding should return a record ID."""
        _, _, mock_collection = mock_chromadb
        # No duplicate exists
        mock_collection.get.return_value = {"ids": [], "metadatas": []}

        result = await vector_store.store_embedding(
            email_id="email-123",
            text="Hello, this is a test email.",
            metadata=sample_metadata,
        )

        assert result == "emb_email-123"

    @pytest.mark.asyncio
    async def test_store_embedding_calls_gemini_embed_content(
        self, vector_store, mock_genai, mock_chromadb, sample_metadata
    ):
        """store_embedding should call genai.embed_content with the correct model."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {"ids": [], "metadatas": []}

        await vector_store.store_embedding(
            email_id="email-123",
            text="Hello, this is a test email.",
            metadata=sample_metadata,
        )

        mock_genai.embed_content.assert_called_once_with(
            model="models/gemini-embedding-001",
            content="Hello, this is a test email.",
        )

    @pytest.mark.asyncio
    async def test_store_embedding_upserts_to_collection(
        self, vector_store, mock_genai, mock_chromadb, sample_metadata
    ):
        """store_embedding should upsert the embedding with metadata to ChromaDB."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {"ids": [], "metadatas": []}

        await vector_store.store_embedding(
            email_id="email-123",
            text="Test email body",
            metadata=sample_metadata,
        )

        mock_collection.upsert.assert_called_once()
        call_kwargs = mock_collection.upsert.call_args[1]
        assert call_kwargs["ids"] == ["emb_email-123"]
        assert call_kwargs["embeddings"] == [[0.1] * 3072]
        assert call_kwargs["documents"] == ["Test email body"]
        assert call_kwargs["metadatas"][0]["email_id"] == "email-123"
        assert call_kwargs["metadatas"][0]["sender"] == "sender@example.com"
        assert call_kwargs["metadatas"][0]["category"] == "Personal"
        assert call_kwargs["metadatas"][0]["provider_message_id"] == "msg-abc-123"
        assert call_kwargs["metadatas"][0]["thread_id"] == "thread-1"
        assert call_kwargs["metadatas"][0]["user_id"] == "user-001"

    @pytest.mark.asyncio
    async def test_store_embedding_without_thread_id(
        self, vector_store, mock_genai, mock_chromadb
    ):
        """store_embedding should not include thread_id when it's None."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {"ids": [], "metadatas": []}
        metadata = EmailMetadata(
            email_id="email-456",
            sender="test@example.com",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            category=EmailCategory.URGENT,
            provider_message_id="msg-456",
            thread_id=None,
            user_id="user-002",
        )

        await vector_store.store_embedding(
            email_id="email-456",
            text="Urgent email",
            metadata=metadata,
        )

        call_kwargs = mock_collection.upsert.call_args[1]
        assert "thread_id" not in call_kwargs["metadatas"][0]
        assert call_kwargs["metadatas"][0]["user_id"] == "user-002"

    @pytest.mark.asyncio
    async def test_store_embedding_skips_duplicate(
        self, vector_store, mock_genai, mock_chromadb, sample_metadata
    ):
        """store_embedding should skip insertion for duplicate provider_message_id."""
        _, _, mock_collection = mock_chromadb
        # Simulate duplicate found
        mock_collection.get.return_value = {
            "ids": ["emb_existing-id"],
            "metadatas": [{"provider_message_id": "msg-abc-123"}],
        }

        result = await vector_store.store_embedding(
            email_id="email-123",
            text="Duplicate email",
            metadata=sample_metadata,
        )

        # Should return existing ID, not create a new one
        assert result == "emb_existing-id"
        # Should NOT call embed_content for duplicates
        mock_genai.embed_content.assert_not_called()
        # Should NOT upsert for duplicates
        mock_collection.upsert.assert_not_called()


# --- Tests for search_similar ---


class TestSearchSimilar:
    """Tests for search_similar method."""

    @pytest.mark.asyncio
    async def test_search_similar_returns_results(
        self, vector_store, mock_genai, mock_chromadb
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

        results = await vector_store.search_similar("test query", k=5)

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        # Similarity = 1 - distance, sorted descending
        assert results[0].similarity_score == pytest.approx(0.9)
        assert results[1].similarity_score == pytest.approx(0.7)
        assert results[0].email_id == "email-1"

    @pytest.mark.asyncio
    async def test_search_similar_uses_gemini_embedding(
        self, vector_store, mock_genai, mock_chromadb
    ):
        """search_similar should generate a query embedding via Gemini."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        await vector_store.search_similar("test query")

        mock_genai.embed_content.assert_called_once_with(
            model="models/gemini-embedding-001",
            content="test query",
        )

    @pytest.mark.asyncio
    async def test_search_similar_passes_k_parameter(
        self, vector_store, mock_genai, mock_chromadb
    ):
        """search_similar should pass k to ChromaDB as n_results."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        await vector_store.search_similar("test query", k=10)

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["n_results"] == 10

    @pytest.mark.asyncio
    async def test_search_similar_empty_results(
        self, vector_store, mock_genai, mock_chromadb
    ):
        """search_similar should return empty list when no results."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        results = await vector_store.search_similar("nothing here")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_similar_with_sender_filter(
        self, vector_store, mock_genai, mock_chromadb
    ):
        """search_similar should pass sender filter to ChromaDB where clause."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        filters = MetadataFilter(sender="alice@example.com")
        await vector_store.search_similar("query", filters=filters)

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"sender": {"$eq": "alice@example.com"}}

    @pytest.mark.asyncio
    async def test_search_similar_with_category_filter(
        self, vector_store, mock_genai, mock_chromadb
    ):
        """search_similar should pass category filter to ChromaDB where clause."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        filters = MetadataFilter(category=EmailCategory.URGENT)
        await vector_store.search_similar("query", filters=filters)

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"category": {"$eq": "Urgent"}}

    @pytest.mark.asyncio
    async def test_search_similar_with_date_range_filter(
        self, vector_store, mock_genai, mock_chromadb
    ):
        """search_similar should pass date range filters to ChromaDB."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [[]],
            "metadatas": [[]],
            "documents": [[]],
            "distances": [[]],
        }

        filters = MetadataFilter(
            date_from=datetime(2024, 1, 1),
            date_to=datetime(2024, 1, 31),
        )
        await vector_store.search_similar("query", filters=filters)

        call_kwargs = mock_collection.query.call_args[1]
        where = call_kwargs["where"]
        assert "$and" in where
        conditions = where["$and"]
        assert {"timestamp": {"$gte": "2024-01-01T00:00:00"}} in conditions
        assert {"timestamp": {"$lte": "2024-01-31T00:00:00"}} in conditions

    @pytest.mark.asyncio
    async def test_search_similar_with_combined_filters(
        self, vector_store, mock_genai, mock_chromadb
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
        await vector_store.search_similar("query", filters=filters)

        call_kwargs = mock_collection.query.call_args[1]
        assert "$and" in call_kwargs["where"]

    @pytest.mark.asyncio
    async def test_search_similar_results_include_metadata(
        self, vector_store, mock_genai, mock_chromadb
    ):
        """search_similar results should include email_id, metadata, and similarity_score."""
        _, _, mock_collection = mock_chromadb
        mock_collection.query.return_value = {
            "ids": [["emb_email-1"]],
            "metadatas": [[
                {
                    "email_id": "email-1",
                    "sender": "alice@example.com",
                    "timestamp": "2024-01-15T10:00:00",
                    "category": "Personal",
                    "provider_message_id": "msg-1",
                    "user_id": "user-001",
                },
            ]],
            "documents": [["Sample email text content for testing"]],
            "distances": [[0.2]],
        }

        results = await vector_store.search_similar("test", k=1)

        assert len(results) == 1
        result = results[0]
        assert result.email_id == "email-1"
        assert result.similarity_score == pytest.approx(0.8)
        assert result.metadata.sender == "alice@example.com"
        assert result.metadata.category == EmailCategory.PERSONAL
        assert result.metadata.provider_message_id == "msg-1"
        assert result.metadata.user_id == "user-001"
        assert result.text_snippet is not None


# --- Tests for delete_by_user ---


class TestDeleteByUser:
    """Tests for delete_by_user method."""

    @pytest.mark.asyncio
    async def test_delete_by_user_returns_count(
        self, vector_store, mock_chromadb
    ):
        """delete_by_user should return count of deleted records."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {
            "ids": ["emb_email-1", "emb_email-2", "emb_email-3"],
            "metadatas": [{}, {}, {}],
        }

        count = await vector_store.delete_by_user("user-001")

        assert count == 3
        mock_collection.delete.assert_called_once_with(
            ids=["emb_email-1", "emb_email-2", "emb_email-3"]
        )

    @pytest.mark.asyncio
    async def test_delete_by_user_no_records(
        self, vector_store, mock_chromadb
    ):
        """delete_by_user should return 0 when no records found."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {
            "ids": [],
            "metadatas": [],
        }

        count = await vector_store.delete_by_user("nonexistent-user")

        assert count == 0
        mock_collection.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_by_user_queries_by_user_id(
        self, vector_store, mock_chromadb
    ):
        """delete_by_user should query ChromaDB with user_id filter."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {
            "ids": ["emb_email-1"],
            "metadatas": [{}],
        }

        await vector_store.delete_by_user("user-xyz")

        mock_collection.get.assert_called_with(
            where={"user_id": "user-xyz"},
            include=["metadatas"],
        )


# --- Tests for is_duplicate ---


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

    def test_is_duplicate_queries_by_provider_message_id(
        self, vector_store, mock_chromadb
    ):
        """is_duplicate should query ChromaDB by provider_message_id."""
        _, _, mock_collection = mock_chromadb
        mock_collection.get.return_value = {
            "ids": [],
            "metadatas": [],
        }

        vector_store.is_duplicate("msg-test-123")

        mock_collection.get.assert_called_with(
            where={"provider_message_id": "msg-test-123"},
            include=["metadatas"],
        )


# --- Tests for _build_where_filter ---


class TestBuildWhereFilter:
    """Tests for internal _build_where_filter method."""

    def test_returns_none_for_no_filters(self, vector_store):
        """Should return None when no filters specified."""
        result = vector_store._build_where_filter(None)
        assert result is None

    def test_returns_none_for_empty_filter(self, vector_store):
        """Should return None when filter has no fields set."""
        filters = MetadataFilter()
        result = vector_store._build_where_filter(filters)
        assert result is None

    def test_single_sender_filter(self, vector_store):
        """Should return direct filter for single condition."""
        filters = MetadataFilter(sender="test@example.com")
        result = vector_store._build_where_filter(filters)
        assert result == {"sender": {"$eq": "test@example.com"}}

    def test_single_category_filter(self, vector_store):
        """Should return direct filter for single category condition."""
        filters = MetadataFilter(category=EmailCategory.SPAM)
        result = vector_store._build_where_filter(filters)
        assert result == {"category": {"$eq": "Spam"}}

    def test_multiple_filters_use_and(self, vector_store):
        """Should combine multiple filters using $and."""
        filters = MetadataFilter(
            sender="test@example.com",
            category=EmailCategory.URGENT,
            date_from=datetime(2024, 1, 1),
        )
        result = vector_store._build_where_filter(filters)
        assert "$and" in result
        assert len(result["$and"]) == 3

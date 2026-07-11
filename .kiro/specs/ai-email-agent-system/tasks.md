# Implementation Plan: AI Email Agent System

## Overview

This implementation plan breaks down the AI-powered multi-agent email management system into incremental coding tasks. The system is built with Python (FastAPI, LangGraph, Celery), uses Gemini for LLM inference, ChromaDB for vector storage, PostgreSQL for structured data, and a React dashboard for human-in-the-loop review. Tasks are ordered to establish foundational infrastructure first, then build agents, then wire integration and API layers, and finally connect the dashboard.

## Tasks

- [x] 1. Set up project structure, core data models, and database schema
  - [x] 1.1 Initialize Python project with dependency management
    - Create project directory structure matching the test infrastructure layout
    - Set up `pyproject.toml` with dependencies: fastapi, uvicorn, langgraph, google-generativeai, chromadb, celery, redis, sqlalchemy, alembic, pydantic, httpx, python-jose, cryptography, hypothesis, pytest, pytest-asyncio
    - Create package structure: `src/agents/`, `src/api/`, `src/services/`, `src/models/`, `src/providers/`, `src/security/`, `src/tasks/`, `tests/`
    - Set up configuration management (environment variables, settings model)
    - _Requirements: 8.1, 6.1_

  - [x] 1.2 Define Pydantic data models and enums
    - Implement all enums: `EmailCategory`, `PriorityLevel`, `DraftStatus`, `WorkflowStage`, `AccountStatus`
    - Implement all Pydantic models: `RawEmail`, `AttachmentMetadata`, `ClassificationResult`, `SummaryResult`, `DraftReply`, `WorkflowState`, `EmailProcessingResult`, `EmailMetadata`, `SearchResult`, `MetadataFilter`, `TokenPair`, `ConnectedAccount`, `PaginatedResponse`, `ReplyAction`, `ErrorResponse`, `FieldError`
    - Add field validators for confidence (0.0-1.0), reply_body (max 500 words), suggested_subject (max 150 chars)
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 3.2, 3.3, 4.7_

  - [x] 1.3 Create PostgreSQL schema and SQLAlchemy models
    - Implement SQLAlchemy ORM models for: `users`, `connected_accounts`, `processed_emails`, `draft_replies`, `access_logs`, `workflow_executions`
    - Create Alembic migration for the full database schema including all indexes
    - Implement repository classes for CRUD operations on each table
    - _Requirements: 1.7, 7.1, 8.1, 10.4_

  - [ ]* 1.4 Write property tests for data model validation
    - **Property 3: ClassificationResult Schema Validity** — Generate arbitrary ClassificationResult instances and verify category, priority, confidence constraints and JSON serialization
    - **Property 10: DraftReply Schema Constraints** — Generate arbitrary DraftReply instances and verify reply_body ≤ 500 words, suggested_subject ≤ 150 chars
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 4.7**

- [x] 2. Implement security and token management
  - [x] 2.1 Implement AES-256 token encryption service
    - Create `TokenEncryptionService` class with `encrypt()` and `decrypt()` methods using AES-256-GCM
    - Use the `cryptography` library (Fernet or AES-GCM via hazmat primitives)
    - Store encryption key reference securely via environment variable
    - _Requirements: 10.1_

  - [x] 2.2 Implement access logging service
    - Create `AccessLogger` class that logs requester_id, endpoint, method, timestamp, response_status
    - Ensure no email body content is included in logs
    - Configure log retention of 90+ days via database storage in `access_logs` table
    - _Requirements: 10.4_

  - [ ]* 2.3 Write property tests for security components
    - **Property 22: Encryption Round-Trip** — For any arbitrary string, encrypt then decrypt produces the original string
    - **Property 23: Access Log Content Safety** — For any log entry, verify it contains requester_id, endpoint, method, timestamp but does NOT contain email body content
    - **Validates: Requirements 10.1, 10.4**

- [x] 3. Implement email provider integration (Gmail and Microsoft Graph)
  - [x] 3.1 Implement OAuth 2.0 manager and abstract provider client
    - Create `OAuthManager` class with `initiate_flow()`, `handle_callback()`, `get_valid_token()`, `revoke_and_delete()` methods
    - Implement proactive token refresh (5 minutes before expiry)
    - Create abstract `EmailProviderClient` base class with `fetch_unread()`, `send_reply()`, `refresh_token()` methods
    - Store tokens encrypted using `TokenEncryptionService`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 3.2 Implement Gmail API client
    - Create `GmailClient` extending `EmailProviderClient`
    - Implement `fetch_unread()` to retrieve emails with full metadata (sender, subject, body, timestamp, attachments)
    - Implement `send_reply()` maintaining thread headers for proper threading
    - Implement retry logic for send failures (1 retry after 5s delay)
    - _Requirements: 1.3, 9.6, 9.7, 9.8_

  - [x] 3.3 Implement Microsoft Graph API client
    - Create `MicrosoftGraphClient` extending `EmailProviderClient`
    - Implement `fetch_unread()` to retrieve emails with full metadata
    - Implement `send_reply()` maintaining thread headers
    - Implement retry logic for send failures (1 retry after 5s delay)
    - _Requirements: 1.3, 9.6, 9.7, 9.8_

  - [ ]* 3.4 Write property tests for token refresh timing
    - **Property 21: Token Refresh Timing** — For any token with expiration time, verify refresh is initiated when remaining time ≤ 5 minutes
    - **Validates: Requirements 9.4**

  - [ ]* 3.5 Write unit tests for email provider clients
    - Test OAuth flow initiation and callback handling
    - Test token refresh on expiry
    - Test send retry logic (success on retry, failure after retry)
    - Test account disconnection flow
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.8_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Email Monitor service
  - [x] 5.1 Implement email monitoring with polling and webhook support
    - Create `EmailMonitor` class with `start_polling()`, `handle_webhook()`, `fetch_emails()`, `enqueue_email()`, `is_duplicate()` methods
    - Implement configurable polling interval (default 60s, min 10s)
    - Implement webhook handler that processes within 5s of notification receipt
    - Implement deduplication using provider_message_id stored in PostgreSQL
    - Extract sender, subject, body, timestamp, attachment metadata from fetched emails
    - _Requirements: 1.1, 1.2, 1.3, 1.7_

  - [x] 5.2 Implement authentication retry and error handling for Email Monitor
    - Implement auth error handling: retry refresh token up to 3 times with 5s delay
    - Implement suspension of polling after auth retry exhaustion, with user notification
    - Implement connectivity failure handling: retry fetch 3x with exponential backoff (2s base)
    - Log all errors with provider name and timestamp
    - _Requirements: 1.4, 1.5, 1.6_

  - [ ]* 5.3 Write property tests for email monitor
    - **Property 1: Email Field Extraction Completeness** — For any valid raw email, extraction produces non-null sender, subject, body, timestamp, and correct attachment metadata
    - **Property 2: Email Deduplication Idempotence** — For any already-processed message_id, re-enqueue attempt is rejected and state store size remains unchanged
    - **Validates: Requirements 1.3, 1.7**

- [x] 6. Implement Classifier Agent
  - [x] 6.1 Implement Classifier Agent with Gemini LLM
    - Create `ClassifierAgent` class with `classify()`, `build_classification_prompt()`, `validate_result()` methods
    - Implement structured prompt for Gemini to produce category, priority, confidence
    - Implement response parsing and validation against ClassificationResult schema
    - Implement 10-second timeout for classification
    - Handle empty email (empty subject + body): assign "Informative", "Low", confidence 0.0
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.9, 2.10_

  - [ ]* 6.2 Write property tests for classification validation and routing
    - **Property 3: ClassificationResult Schema Validity** — Validate that any produced ClassificationResult has valid category, priority, confidence values
    - **Property 4: Classification Routing Correctness** — For any ClassificationResult, verify routing to Response_Agent for Urgent/Personal + High/Medium, to Summarizer_Agent for other categories or Low priority, and manual review for confidence < 0.6
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**

- [x] 7. Implement Summarizer Agent
  - [x] 7.1 Implement Summarizer Agent with Gemini LLM
    - Create `SummarizerAgent` class with `summarize()`, `should_summarize()`, `build_summary_prompt()`, `fallback_summary()` methods
    - Implement word count check (200 word threshold)
    - Implement summary generation with max 3 sentences and up to 10 action items
    - Implement 8-second timeout
    - Implement fallback: return first 3 sentences when LLM fails or times out
    - Handle no-content emails: return indication that no summary could be generated
    - For emails < 200 words: return original body unmodified
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [ ]* 7.2 Write property tests for summarization
    - **Property 5: Summarization Routing Threshold** — For any email with category Urgent/Informative and body > 200 words, verify routing to Summarizer_Agent
    - **Property 6: Summary Output Constraints** — For any SummaryResult, verify summary ≤ 3 sentences and action_items ≤ 10 items
    - **Property 7: Short Email Passthrough Identity** — For any email body < 200 words, verify the summary equals the original body unmodified
    - **Property 8: Fallback Summary Extraction** — For any email body, verify fallback extracts first 3 sentences and marks as fallback
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.7**

- [x] 8. Implement Vector Store service
  - [x] 8.1 Implement ChromaDB vector store service
    - Create `VectorStoreService` class with `store_embedding()`, `search_similar()`, `delete_by_user()`, `is_duplicate()` methods
    - Use `gemini-embedding-001` for generating 3072-dimensional embeddings via google-generativeai SDK
    - Implement cosine similarity search with configurable k parameter
    - Implement metadata filtering (sender, date_range, category) applied before similarity ranking
    - Implement deduplication check by provider_message_id
    - Ensure search completes within 2 seconds for up to 100k stored emails
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 8.2 Write property tests for vector store
    - **Property 11: Vector Search Results Ordering and Count** — For any search with parameter k, verify at most k results returned in descending similarity order
    - **Property 12: Vector Metadata Filter Correctness** — For any search with metadata filters, verify all results satisfy every filter criterion
    - **Property 13: Vector Embedding Deduplication** — For any duplicate provider_message_id submission, verify no duplicate entry created and existing ID returned
    - **Validates: Requirements 5.2, 5.4, 5.5, 5.6**

- [x] 9. Implement Response Agent
  - [x] 9.1 Implement Response Agent with historical context retrieval
    - Create `ResponseAgent` class with `generate_reply()`, `retrieve_context()`, `build_response_prompt()`, `validate_draft()` methods
    - Implement semantic search for top-5 similar past emails using VectorStoreService
    - Implement tone matching from historical emails (sentence structure, greeting/sign-off style, average sentence length)
    - Implement 15-second timeout with discard of partial draft on timeout
    - If no relevant history (all similarity scores < 0.3): generate with neutral professional tone
    - Enforce output constraints: max 500 words body, max 150 chars subject, include referenced_email_ids
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [ ]* 9.2 Write property tests for response agent
    - **Property 9: Historical Context Threshold Decision** — For any search results where all similarity scores < 0.3, verify draft uses neutral tone without historical context
    - **Property 10: DraftReply Schema Constraints** — For any DraftReply, verify reply_body ≤ 500 words, suggested_subject ≤ 150 chars
    - **Validates: Requirements 4.6, 4.7**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement Agent Orchestrator with LangGraph
  - [x] 11.1 Build LangGraph StateGraph workflow
    - Create `build_email_workflow()` function constructing the LangGraph StateGraph
    - Define `EmailWorkflowState` TypedDict with all intermediate fields
    - Implement `route_after_classification()` conditional routing node
    - Wire Classifier → route decision → Summarizer/Response/ManualReview → PublishResults
    - Implement the dual path: Urgent emails with body > 200 words get both summarization and response generation
    - _Requirements: 6.1, 2.7, 2.8, 3.1_

  - [x] 11.2 Implement retry logic and failure handling in orchestrator
    - Create `AgentOrchestrator` class with `process_email()` and `handle_agent_failure()` methods
    - Implement per-agent retry up to 3 attempts on unhandled exceptions
    - Implement 30-second hard timeout per agent execution
    - On retry exhaustion: mark email as failed, skip remaining agents, move to next email
    - Implement concurrent processing support for up to 10 simultaneous emails with isolated state
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.7_

  - [x] 11.3 Implement result publishing and workflow completion
    - When all designated agents complete, aggregate results (classification + summary + draft reply)
    - Publish aggregated results to Dashboard via WebSocket notification
    - Store processing results in PostgreSQL
    - Store email embedding in ChromaDB
    - _Requirements: 6.6, 5.1_

  - [ ]* 11.4 Write property tests for orchestration
    - **Property 14: Workflow Retry Count Invariant** — For any agent execution, verify retry count never exceeds 3 and pipeline terminates after exhaustion
    - **Property 15: Workflow State Isolation** — For any set of concurrent workflows, verify mutations to one workflow's state are not observable in another
    - **Validates: Requirements 6.2, 6.3, 6.5**

- [x] 12. Implement Celery task layer for background processing
  - [x] 12.1 Configure Celery with Redis and implement email processing tasks
    - Set up Celery app configuration with Redis as broker and result backend
    - Create `process_email_task` Celery task that invokes AgentOrchestrator
    - Create `poll_emails_task` periodic Celery task for email monitoring
    - Configure concurrency to support up to 10 simultaneous workflow executions
    - Implement task retry policies matching orchestrator retry logic
    - _Requirements: 6.5, 1.1_

  - [ ]* 12.2 Write integration tests for Celery tasks
    - Test task enqueueing and execution with mocked agents
    - Test retry behavior on agent failures
    - Test concurrent task isolation
    - _Requirements: 6.2, 6.3, 6.5_

- [x] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement FastAPI backend and API layer
  - [x] 14.1 Implement API authentication and middleware
    - Create API key and OAuth token authentication middleware
    - Implement request validation middleware (return 422 with field-level errors)
    - Implement access logging middleware (using AccessLogger, no body content in logs)
    - Return 401 for unauthenticated requests without processing
    - _Requirements: 8.5, 8.6, 8.7, 10.4_

  - [x] 14.2 Implement email list and detail endpoints
    - `GET /api/v1/emails` — paginated list with filters (category, priority, date_range), default page_size=20, max=100, sorted by processing_timestamp desc
    - `GET /api/v1/emails/{id}` — full processing result (classification, summary, draft reply)
    - `GET /api/v1/emails/review` — emails flagged for manual review (confidence < 0.75)
    - Return 404 for non-existent email IDs
    - _Requirements: 8.1, 8.2, 8.8, 7.1, 7.2, 7.8_

  - [x] 14.3 Implement draft reply action endpoints
    - `POST /api/v1/emails/{id}/reply/approve` — approve and send draft via email provider
    - `POST /api/v1/emails/{id}/reply/reject` — reject draft and mark for manual response
    - Support edited body (max 10,000 chars) and subject (max 255 chars) on approval
    - Return 409 for already-actioned drafts
    - Return 404 for non-existent drafts
    - Implement send confirmation within 30 seconds
    - Handle send failures: display error, retain draft, allow retry
    - _Requirements: 8.3, 8.9, 7.4, 7.5, 7.6, 7.7, 7.9_

  - [x] 14.4 Implement manual fetch and WebSocket endpoints
    - `POST /api/v1/emails/fetch` — trigger manual email fetch, return acknowledgment
    - `WS /api/v1/ws` — WebSocket endpoint for real-time processing updates to Dashboard
    - _Requirements: 8.4, 6.6_

  - [ ]* 14.5 Write property tests for API layer
    - **Property 16: API Pagination Correctness** — For any paginated request, verify at most min(page_size, 100) items returned, default 20, sorted desc by timestamp
    - **Property 17: API Request Validation** — For any invalid payload, verify 422 returned with field-level error messages
    - **Property 18: API Authentication Enforcement** — For any request without valid credentials, verify 401 returned without processing
    - **Property 19: API 404 for Missing Resources** — For any non-existent ID, verify 404 returned
    - **Property 20: API 409 for Already-Actioned Drafts** — For any already-processed draft, verify 409 returned
    - **Validates: Requirements 8.1, 8.5, 8.6, 8.7, 8.8, 8.9**

- [x] 15. Implement account management and data deletion
  - [x] 15.1 Implement account connection and disconnection flows
    - Create API endpoints for initiating OAuth connection (`GET /api/v1/auth/{provider}/connect`)
    - Create callback endpoint for OAuth code exchange (`GET /api/v1/auth/{provider}/callback`)
    - Implement account disconnection endpoint that triggers full data deletion
    - Delete all stored tokens, embeddings, and processing results within 24 hours
    - Retry deletion up to 3 times if it fails
    - Notify user on deletion completion or failure
    - _Requirements: 9.1, 9.2, 9.3, 10.5, 10.6, 10.7_

  - [ ]* 15.2 Write property tests for account deletion
    - **Property 24: Account Deletion Completeness** — For any disconnection request, verify zero tokens, zero embeddings, zero processing results remain for that user
    - **Validates: Requirements 10.5**

- [x] 16. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Implement React Dashboard frontend
  - [x] 17.1 Set up React project with routing and state management
    - Initialize React project with TypeScript, React Router, and state management (e.g., Zustand or React Query)
    - Create API client module for communicating with FastAPI backend
    - Set up WebSocket client for real-time updates
    - Implement authentication flow (API key or OAuth token management in frontend)
    - _Requirements: 7.1, 8.6_

  - [x] 17.2 Implement email list view with filtering and pagination
    - Create paginated email list component showing category, priority, confidence (0.00-1.00), processing timestamp
    - Maximum 50 emails per page display
    - Implement filters by category, priority, and date range
    - Display emails flagged for manual review in a distinct visual section
    - _Requirements: 7.1, 7.2, 7.8_

  - [x] 17.3 Implement email detail view with summary and draft reply
    - Create detail view showing full email content, summary (if generated), and draft reply (if generated)
    - Implement approve, edit, and reject controls for draft replies
    - Allow free-text editing of reply body (max 10,000 chars) and subject (max 255 chars)
    - Display sent confirmation status after approval
    - Display error messages on send failure with retry option
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.7, 7.9_

  - [x] 17.4 Implement account connection UI and notifications
    - Create account connection/disconnection interface (OAuth redirect flow)
    - Display connection status and handle re-authentication notifications
    - Show error messages for denied consent or cancelled OAuth flow
    - Display user notifications for auth failures, send failures, deletion status
    - _Requirements: 9.2, 9.3, 9.5, 1.5_

- [x] 18. Integration wiring and end-to-end flow validation
  - [x] 18.1 Wire complete email processing pipeline end-to-end
    - Connect Email Monitor → Celery queue → LangGraph Orchestrator → Agents → Result storage → WebSocket notification
    - Verify full pipeline with mocked LLM responses: email fetch → classify → summarize/respond → store → notify dashboard
    - Ensure proper error propagation and graceful degradation across all components
    - Configure circuit breaker pattern for external service calls (Email Provider API, Gemini API)
    - _Requirements: 6.1, 6.6, 1.1, 1.2_

  - [ ]* 18.2 Write integration tests for end-to-end pipeline
    - Test full pipeline with mocked LLM and real PostgreSQL/ChromaDB
    - Test WebSocket notification delivery to connected clients
    - Test error recovery and graceful degradation scenarios
    - Test concurrent workflow execution with state isolation
    - _Requirements: 6.1, 6.5, 6.6_

- [x] 19. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation of each major system layer
- Property tests validate universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- The Gemini LLM calls should be mocked in all tests except dedicated integration tests with real API credentials
- All token storage must use AES-256 encryption via the `TokenEncryptionService`
- The system uses Hypothesis as the property-based testing library with minimum 100 examples per property

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3"] },
    { "id": 5, "tasks": ["3.4", "3.5", "5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 7, "tasks": ["6.2", "7.1", "8.1"] },
    { "id": 8, "tasks": ["7.2", "8.2", "9.1"] },
    { "id": 9, "tasks": ["9.2", "11.1"] },
    { "id": 10, "tasks": ["11.2", "11.3"] },
    { "id": 11, "tasks": ["11.4", "12.1"] },
    { "id": 12, "tasks": ["12.2", "14.1"] },
    { "id": 13, "tasks": ["14.2", "14.3", "14.4"] },
    { "id": 14, "tasks": ["14.5", "15.1"] },
    { "id": 15, "tasks": ["15.2", "17.1"] },
    { "id": 16, "tasks": ["17.2", "17.3", "17.4"] },
    { "id": 17, "tasks": ["18.1"] },
    { "id": 18, "tasks": ["18.2"] }
  ]
}
```

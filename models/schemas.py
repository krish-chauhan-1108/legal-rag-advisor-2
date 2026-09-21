"""
Pydantic schemas for request/response validation across the Legal RAG Advisor.

Every API boundary is strictly typed to catch malformed payloads early and
produce self-documenting OpenAPI specs.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Ingestion Schemas
# =============================================================================

class DocumentMetadata(BaseModel):
    """Metadata attached to every ingested chunk."""

    document_name: str = Field(
        ...,
        description="Original filename of the uploaded document.",
    )
    section: str = Field(
        default="General",
        description="Detected section heading (e.g., 'Article 5 — Indemnification').",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO-8601 timestamp of when the document was ingested.",
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Source page number in the original PDF (1-indexed).",
    )
    chunk_index: int = Field(
        default=0,
        description="Sequential index of this chunk within the document.",
    )


class IngestionRequest(BaseModel):
    """
    Request body for the ``/api/ingest`` endpoint.

    The actual file is sent as multipart form data; this model captures
    optional metadata overrides sent alongside it.
    """

    document_name: Optional[str] = Field(
        default=None,
        description="Override for the document name (defaults to the uploaded filename).",
    )


class IngestionResponse(BaseModel):
    """Response returned after a successful document ingestion."""

    status: str = Field(
        default="success",
        description="Ingestion status.",
    )
    document_names: list[str] = Field(
        ...,
        description="Names of the ingested documents.",
    )
    total_chunks: int = Field(
        ...,
        description="Number of chunks created from the document.",
    )
    message: str = Field(
        default="",
        description="Human-readable summary.",
    )


# =============================================================================
# Analysis / Chat Schemas
# =============================================================================


class ChatSessionCreate(BaseModel):
    title: str

class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    structured_content: Optional[dict] = None
    sources: Optional[list] = None
    model_used: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    created_at: str

class ChatSessionResponse(BaseModel):
    id: str
    title: str
    user_email: str
    messages: list[ChatMessageResponse] = []
    created_at: str
    updated_at: str


class GoogleAuthRequest(BaseModel):
    credential: str = Field(..., min_length=20)


class AuthenticatedUserResponse(BaseModel):
    id: str
    google_id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


class GoogleAuthResponse(BaseModel):
    user: AuthenticatedUserResponse


class AnalysisRequest(BaseModel):
    """Request body for the ``/api/analyze`` endpoint."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The legal question or analysis request from the user.",
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="Optional: ID of the chat session to persist messages.",
    )
    document_filter: Optional[str] = Field(
        default=None,
        description="Optional: restrict retrieval to a specific document name.",
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Override the default number of chunks to retrieve before reranking.",
    )

    model_preference: Optional[str] = Field(
        default="deep",
        description="Model preference: 'deep' for 31B or 'quick' for 2.5-flash.",
    )
    ephemeral_context: Optional[str] = Field(
        default=None,
        description="Optional: Raw text extracted from an ephemeral document upload for this query.",
    )


class SourceChunk(BaseModel):
    """A single source chunk surfaced alongside the analysis."""

    content: str = Field(
        ...,
        description="Text content of the retrieved chunk.",
    )
    document_name: str = Field(
        ...,
        description="Originating document.",
    )
    section: str = Field(
        default="General",
        description="Section heading within the document.",
    )
    relevance_score: float = Field(
        default=0.0,
        description="Relevance score from the reranker (0–1).",
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Page number in the original PDF.",
    )


class ApplicableLaw(BaseModel):
    code: str = Field(default="", description="The legal code, e.g. BNS, BNSS")
    section: str = Field(default="", description="The exact section and sub-section")
    quote: str = Field(default="", description="Exact wording or excerpt")
    explanation: str = Field(default="", description="Simple explanation of this section")

class StructuredAnalysis(BaseModel):
    """The structured JSON payload returned by the LLM."""
    is_conversational: bool = Field(default=False, description="True if the query was just small talk")
    conversational_reply: Optional[str] = Field(default=None, description="The conversational reply if is_conversational is True")
    requires_sources: bool = Field(default=True, description="False if this is a simple yes/no, conversational, or general query where explicitly showing legal sources is unnecessary.")
    suggest_lawyer: bool = Field(default=False, description="True if the user's situation is severe or complex enough that they should consult a real lawyer.")
    general_analysis: str = Field(default="", description="1. General Legal Analysis (Use this for general questions like 'What is the difference between X and Y'). Leave empty if it's a specific personal situation.")
    situation_meaning: str = Field(default="", description="1. What the situation means")
    bail_status: str = Field(default="", description="2. Bail Status")
    next_24_hours: list[str] = Field(default_factory=list, description="3. What to do in the next 24 hours (Step-by-Step)")
    rights: list[str] = Field(default_factory=list, description="4. Your Rights")
    handling_authority: str = Field(default="", description="5. Which Authority handles this?")
    applicable_laws: list[ApplicableLaw] = Field(default_factory=list, description="List of applicable laws")
    relevant_source_indices: list[int] = Field(default_factory=list, description="List of source chunk indices (1-based, e.g. [1, 3]) from the provided context that were ACTUALLY relevant. Exclude irrelevant chunks.")

class AnalysisResponse(BaseModel):
    """Structured response from the ``/api/analyze`` endpoint."""

    query: str = Field(
        ...,
        description="The original query echoed back for traceability.",
    )
    analysis: StructuredAnalysis = Field(
        ...,
        description="The AI Legal Advisor's structured analysis.",
    )
    sources: list[SourceChunk] = Field(
        default_factory=list,
        description="Ranked source chunks that grounded the analysis.",
    )
    model_used: str = Field(
        default="",
        description="Identifier of the LLM used for generation.",
    )
    processing_time_seconds: float = Field(
        default=0.0,
        description="Wall-clock time for the full retrieval + generation pipeline.",
    )


# =============================================================================
# Health Check
# =============================================================================

class HealthResponse(BaseModel):
    """Response for the ``/health`` endpoint."""

    status: str = "healthy"
    version: str = "1.0.0"
    documents_indexed: int = 0
    vector_store_ready: bool = False

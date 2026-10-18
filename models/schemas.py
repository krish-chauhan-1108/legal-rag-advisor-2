"""
Pydantic schemas for request/response validation across the Legal RAG Advisor.

Every API boundary is strictly typed to catch malformed payloads early and
produce self-documenting OpenAPI specs.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


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


class ChatSessionSummaryResponse(BaseModel):
    id: str
    title: str
    user_email: str
    created_at: str
    updated_at: str


class ChatAttachmentResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    created_at: str


class ChatAttachmentsResponse(BaseModel):
    attachments: list[ChatAttachmentResponse] = Field(default_factory=list)


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
    session_token: str
    session_expires_at: str


class AdminAccessResponse(BaseModel):
    email: str
    is_admin: bool


class AdminAPIKeyCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    api_key: str = Field(..., min_length=20, max_length=512)
    provider: str = Field(default="google", min_length=1, max_length=64)
    model: str = Field(default="gemini-2.5-flash", min_length=1, max_length=160)
    mode: Literal["quick", "deep"] = "quick"
    base_url: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True
    rotation_order: Optional[int] = Field(default=None, ge=0)


class AdminAPIKeyUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=64)
    model: Optional[str] = Field(default=None, min_length=1, max_length=160)
    mode: Optional[Literal["quick", "deep"]] = None
    base_url: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None
    rotation_order: Optional[int] = Field(default=None, ge=0)


class AdminAPIKeyResponse(BaseModel):
    id: str
    label: str
    provider: str = "google"
    model: str = "gemini-2.5-flash"
    mode: Literal["quick", "deep"] = "quick"
    base_url: Optional[str] = None
    fingerprint: str
    masked_key: str
    is_active: bool
    rotation_order: int
    created_at: str
    updated_at: str
    last_used_at: Optional[str] = None
    last_error_status: Optional[str] = None
    last_error_at: Optional[str] = None


class AdminUsageCounts(BaseModel):
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    quota_failures: int = 0


class AdminUsageRow(BaseModel):
    api_key_id: str
    label: str
    masked_key: str
    provider: str = "google"
    model: str
    mode: Literal["quick", "deep"] = "quick"
    minute: AdminUsageCounts
    day: AdminUsageCounts
    all_time: AdminUsageCounts


class AdminUsageResponse(BaseModel):
    timezone: str = "Asia/Kolkata"
    current_minute_start: str
    current_day_start: str
    rows: list[AdminUsageRow] = Field(default_factory=list)


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
        description="Deprecated compatibility field; normal analysis no longer uses local retrieval.",
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Deprecated compatibility field; normal analysis no longer retrieves chunks.",
    )

    model_preference: Optional[str] = Field(
        default="quick",
        description="Compatibility field; TRANA uses the Quick Thinking provider rotation.",
    )
    ephemeral_context: Optional[str] = Field(
        default=None,
        description="Optional: Raw text extracted from an ephemeral document upload for this query.",
    )


class TemporaryConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


class TemporaryAnalysisRequest(AnalysisRequest):
    """Guest analysis request with bounded, client-held conversation context."""

    conversation_history: list[TemporaryConversationMessage] = Field(default_factory=list, max_length=20)


class SourceChunk(BaseModel):
    """A verified legal source or legacy uploaded-document source."""

    content: str = Field(
        ...,
        description="Text content of the source.",
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
        description="Legacy ranking score; verified registry sources use 0.0.",
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Page number in the original PDF.",
    )
    act: Optional[str] = Field(default=None, description="Full name of the legal Act.")
    code: Optional[str] = Field(default=None, description="Short legal code, such as BNS, BNSS, or BSA.")
    subsection: Optional[str] = Field(default=None, description="Subsection within the cited section.")
    exact_text: Optional[str] = Field(default=None, description="Exact text from the verified source registry.")
    quote: str = Field(default="", description="Backend-populated exact wording; never trusted from the LLM.")
    verified: bool = Field(default=False, description="Whether the source text was resolved from the backend registry.")
    source_url: Optional[str] = Field(default=None, description="Authoritative source URL.")
    source_version: Optional[str] = Field(default=None, description="Version of the authoritative source.")
    source_hash: Optional[str] = Field(default=None, description="SHA-256 hash of the exact source text.")
    quote_status: str = Field(default="unverified", description="backend_verified or unverified.")


class ApplicableLaw(BaseModel):
    act: str = Field(default="", description="The Act name or legal code as returned by the model.")
    code: str = Field(default="", description="The legal code, e.g. BNS, BNSS")
    section: str = Field(default="", description="The exact section and sub-section")
    subsection: Optional[str] = Field(default=None, description="The subsection, when separately identified.")
    quote: str = Field(default="", description="Backend-populated exact wording; never trusted from the LLM")
    explanation: str = Field(default="", description="Simple explanation of this section")
    exact_text: Optional[str] = Field(default=None, description="Exact text from the verified source registry")
    source_url: Optional[str] = Field(default=None, description="Authoritative source URL")
    source_version: Optional[str] = Field(default=None, description="Version of the authoritative source")
    source_hash: Optional[str] = Field(default=None, description="SHA-256 hash of exact_text")
    quote_status: str = Field(default="unverified", description="backend_verified or unverified")
    verified: bool = Field(default=False, description="Whether exact_text was resolved from the backend registry")

    @model_validator(mode="after")
    def synchronize_act_and_code(self) -> "ApplicableLaw":
        """Accept either model naming convention without discarding its value."""

        if not self.code and self.act:
            self.code = self.act
        elif not self.act and self.code:
            self.act = self.code
        return self

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
    relevant_source_indices: list[int] = Field(default_factory=list, description="Deprecated legacy chunk indices.")

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
        description="Verified legal sources returned alongside the analysis.",
    )
    model_used: str = Field(
        default="",
        description="Identifier of the LLM used for generation.",
    )
    processing_time_seconds: float = Field(
        default=0.0,
        description="Wall-clock time for direct generation and source verification.",
    )


# =============================================================================
# Health Check
# =============================================================================

class HealthResponse(BaseModel):
    """Response for the ``/health`` endpoint."""

    status: str = "healthy"
    version: str = "1.0.0"
    build_id: str = "unknown"
    source_registry_ready: bool = False
    documents_indexed: int = 0
    vector_store_ready: bool = False

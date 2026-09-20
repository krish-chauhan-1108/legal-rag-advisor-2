"""
TRANA — FastAPI Application
=======================================

A production-ready AI Legal Advisor API that:

  • Ingests legal PDF documents (agreements, case files, contracts).
  • Chunks them with structure-aware splitting that respects section
    boundaries.
  • Stores embeddings in a persistent ChromaDB vector store.
  • Answers legal questions via a hybrid retrieval pipeline (dense + BM25)
    with cross-encoder reranking and a strictly grounded LLM.

Endpoints
---------
  POST /api/ingest      — Upload and ingest a PDF document.
  POST /api/analyze     — Ask a legal question and receive structured analysis.
  GET  /api/documents   — List all ingested documents.
  DELETE /api/documents — Delete a specific document from the index.
  GET  /health          — Health check with system status.

Usage
-----
  $ uvicorn main:app --reload

  # Or directly:
  $ python main.py
"""

from __future__ import annotations

import shutil
import secrets
import time
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

print("[Progress] Loading config and settings...")
from config import settings

from database import engine, get_db, Base
import models.db_models as db_models
import json
import sqlite3

print("[Progress] Loading schemas...")
from models.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    HealthResponse,
    IngestionResponse,
    ChatSessionCreate,
    ChatSessionResponse,
    ChatMessageResponse,
    GoogleAuthRequest,
    GoogleAuthResponse,
)
from key_manager import rotate_key

print("[Progress] Loading Logger...")
from utils.logger import get_logger

logger = get_logger(__name__)

_health_documents_indexed = 0
_health_vector_store_ready = False


def _get_persisted_chunk_count() -> int:
    """Read the persisted Chroma chunk count without initializing embeddings."""
    chroma_db = Path(settings.chroma_persist_dir) / "chroma.sqlite3"
    if not chroma_db.is_file():
        return 0

    try:
        with sqlite3.connect(f"file:{chroma_db}?mode=ro", uri=True) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])
    except (sqlite3.Error, TypeError, ValueError) as exc:
        logger.warning("Could not read persisted Chroma chunk count: %s", exc)
        return 0


# ═══════════════════════════════════════════════════════════════════════════
# Application Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown lifecycle manager.

    On startup:
      - Ensure required directories exist.
      - Initialize the configured SQL schema.

    Heavy RAG modules are loaded lazily by the endpoints that need them. This
    lets Uvicorn bind Render's port before importing the document-processing
    and retrieval stack.

    On shutdown:
      - Log a clean shutdown message.
    """
    logger.info("=" * 60)
    logger.info("  TRANA — Starting up")
    logger.info("=" * 60)

    # Ensure data directories exist.
    print("[Progress] Ensuring data directories exist...")
    settings.ensure_directories()
    print("[Progress] Ensuring STATIC_DIR exists...")
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    
    print("[Progress] Initializing application database...")
    db_models.Base.metadata.create_all(bind=engine)

    print("[Progress] Application startup logic complete.")
    logger.info("Startup complete. Server ready on http://%s:%d", settings.host, settings.port)
    logger.info("=" * 60)
    global _health_documents_indexed, _health_vector_store_ready
    _health_documents_indexed = _get_persisted_chunk_count()
    _health_vector_store_ready = (Path(settings.chroma_persist_dir) / "chroma.sqlite3").exists()

    yield  # ← Application runs here.

    logger.info("TRANA — Shutting down gracefully.")


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="TRANA",
    description=(
        "AI-powered legal document analysis API. Upload contracts and legal "
        "agreements, then ask natural-language questions to receive structured, "
        "grounded analysis with source citations."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS — allow all origins during development ────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve the frontend SPA ──────────────────────────────────────────────────
STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def api_root():
    """Identify the backend; the user-facing frontend is deployed on Vercel."""
    return {
        "service": "trana-api",
        "frontend": "deployed separately",
        "health": "/health",
        "docs": "/docs",
    }


def _verify_google_credential(credential: str) -> dict:
    """Verify a Google ID token and return its trusted claims."""
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on the backend.")

    try:
        claims = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except (ValueError, TypeError) as exc:
        logger.warning("Rejected invalid Google credential: %s", exc)
        raise HTTPException(status_code=401, detail="Your Google sign-in has expired or is invalid.") from exc

    issuer = claims.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=401, detail="The sign-in issuer is not Google.")
    if not claims.get("email") or not claims.get("email_verified"):
        raise HTTPException(status_code=401, detail="A verified Google email is required.")
    return claims


def get_current_user_email(authorization: str | None = Header(default=None)) -> str:
    """Return the verified Google email for authenticated user-facing requests."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in with Google to use chat history.")
    claims = _verify_google_credential(authorization.split(" ", 1)[1].strip())
    return str(claims["email"])


@app.post("/api/auth/google", response_model=GoogleAuthResponse, tags=["Authentication"])
def authenticate_google(auth_in: GoogleAuthRequest, db: Session = Depends(get_db)):
    """Verify a Google credential and upsert the corresponding application user."""
    claims = _verify_google_credential(auth_in.credential)
    google_id = str(claims["sub"])
    email = str(claims["email"])
    user = db.query(db_models.User).filter(db_models.User.google_id == google_id).first()
    if user is None:
        user = db.query(db_models.User).filter(db_models.User.email == email).first()
    if user is None:
        user = db_models.User(google_id=google_id, email=email)
        db.add(user)

    user.google_id = google_id
    user.email = email
    user.name = claims.get("name")
    user.picture = claims.get("picture")
    db.commit()
    db.refresh(user)
    return {"user": user}


# ═══════════════════════════════════════════════════════════════════════════
# Chat Sessions API
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/chats", response_model=list[ChatSessionResponse], tags=["Chats"])
def get_chats(user_email: str = Depends(get_current_user_email), db: Session = Depends(get_db)):
    sessions = db.query(db_models.ChatSession).filter(db_models.ChatSession.user_email == user_email).order_by(db_models.ChatSession.updated_at.desc()).all()
    res = []
    for s in sessions:
        msgs = db.query(db_models.ChatMessage).filter(db_models.ChatMessage.session_id == s.id).order_by(db_models.ChatMessage.created_at.asc()).all()
        parsed_msgs = []
        for m in msgs:
            parsed_msgs.append({
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "structured_content": json.loads(m.structured_content) if m.structured_content else None,
                "sources": json.loads(m.sources) if m.sources else None,
                "created_at": m.created_at.isoformat()
            })
        res.append({
            "id": s.id,
            "title": s.title,
            "user_email": s.user_email,
            "messages": parsed_msgs,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat()
        })
    return res

@app.post("/api/chats", response_model=ChatSessionResponse, tags=["Chats"])
def create_chat(chat_in: ChatSessionCreate, user_email: str = Depends(get_current_user_email), db: Session = Depends(get_db)):
    import uuid
    new_id = str(uuid.uuid4())
    db_session = db_models.ChatSession(
        id=new_id,
        user_email=user_email,
        title=chat_in.title
    )
    db.add(db_session)
    
    # Add initial TRANA message
    init_msg = db_models.ChatMessage(
        session_id=new_id,
        role="assistant",
        content="I'm TRANA—your friendly legal assistant. How can I help you today?"
    )
    db.add(init_msg)
    
    db.commit()
    db.refresh(db_session)
    return {
        "id": db_session.id,
        "title": db_session.title,
        "user_email": db_session.user_email,
        "messages": [{
            "id": init_msg.id,
            "role": init_msg.role,
            "content": init_msg.content,
            "created_at": init_msg.created_at.isoformat()
        }],
        "created_at": db_session.created_at.isoformat(),
        "updated_at": db_session.updated_at.isoformat()
    }

@app.delete("/api/chats/{chat_id}", tags=["Chats"])
def delete_chat(chat_id: str, user_email: str = Depends(get_current_user_email), db: Session = Depends(get_db)):
    db_session = db.query(db_models.ChatSession).filter(db_models.ChatSession.id == chat_id, db_models.ChatSession.user_email == user_email).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Chat not found")
    db.query(db_models.ChatMessage).filter(db_models.ChatMessage.session_id == chat_id).delete()
    db.delete(db_session)
    db.commit()
    return {"status": "success"}

# ═══════════════════════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════════════════════

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check and system status",
)
async def health_check() -> HealthResponse:
    """
    Return the health status of TRANA.

    Includes the number of indexed document chunks and whether the vector
    store is operational.
    """
    global _health_documents_indexed, _health_vector_store_ready
    _health_documents_indexed = _get_persisted_chunk_count()
    _health_vector_store_ready = (Path(settings.chroma_persist_dir) / "chroma.sqlite3").exists()

    return HealthResponse(
        status="healthy",
        documents_indexed=_health_documents_indexed,
        vector_store_ready=_health_vector_store_ready,
    )


# ═══════════════════════════════════════════════════════════════════════════
# One-time Seed Snapshot Import
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _safe_extract_seed_archive(archive_path: Path) -> None:
    """Extract only the application database and Chroma snapshot paths."""
    project_root = Path(__file__).resolve().parent
    allowed_root = project_root.resolve()

    with ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_name = member.filename.replace("\\", "/")
            path_parts = PurePosixPath(member_name).parts
            if (
                not member_name
                or member_name.startswith("/")
                or ".." in path_parts
                or (path_parts[0] not in {"legal.db", "data"})
            ):
                raise ValueError(f"Seed archive contains an unsafe path: {member.filename}")

            destination = (project_root / member_name).resolve()
            try:
                destination.relative_to(allowed_root)
            except ValueError as exc:
                raise ValueError(f"Seed archive escapes the application directory: {member.filename}") from exc

            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)

    chroma_dir = (project_root / settings.chroma_persist_dir).resolve()
    if not (project_root / "legal.db").is_file() or not chroma_dir.is_dir():
        raise ValueError("Seed archive must contain legal.db and data/chroma_db.")


@app.post("/api/admin/import-seed", tags=["Admin"], include_in_schema=False)
def import_seed_snapshot(
    archive: UploadFile = File(...),
    x_seed_token: str | None = Header(default=None),
) -> dict:
    """Replace the local SQLite/Chroma state with a supplied ZIP snapshot."""
    expected_token = settings.seed_upload_token
    if not expected_token or not x_seed_token or not secrets.compare_digest(x_seed_token, expected_token):
        raise HTTPException(status_code=403, detail="Seed import is not authorized.")

    if not archive.filename or not archive.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a ZIP seed archive.")

    settings.ensure_directories()
    temp_archive = Path(settings.upload_dir) / ".seed-upload.zip"
    try:
        with temp_archive.open("wb") as destination:
            shutil.copyfileobj(archive.file, destination)
        try:
            _safe_extract_seed_archive(temp_archive)
        except (BadZipFile, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid seed archive: {exc}") from exc

        # Drop cached handles so the next request reads the imported snapshot.
        from database import engine as database_engine
        database_engine.dispose()
        import retrieval.bm25_retriever as bm25_module
        import retrieval.vector_store as vector_module
        bm25_module._bm25_retriever = None
        vector_module._embedding_function = None
        vector_module._vector_store = None
        global _health_documents_indexed, _health_vector_store_ready
        _health_documents_indexed = _get_persisted_chunk_count()
        _health_vector_store_ready = True

        return {
            "status": "success",
            "message": "Seed snapshot imported. The existing SQLite and Chroma data are now active.",
            "restart_recommended": True,
        }
    finally:
        temp_archive.unlink(missing_ok=True)


# Document Ingestion
# ═══════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/ingest",
    response_model=IngestionResponse,
    tags=["Ingestion"],
    summary="Upload and ingest multiple legal PDF documents",
)
def ingest_document(
    files: list[UploadFile] = File(
        ...,
        description="A list of PDF files containing legal documents to ingest.",
    )
) -> IngestionResponse:
    """
    Upload PDFs, parse them, chunk them with section-aware splitting, embed
    the chunks, and store them in the vector database.
    """
    from ingestion.chunker import chunk_document
    from ingestion.parser import parse_pdf
    from retrieval.bm25_retriever import rebuild_bm25_from_vector_store
    from retrieval.vector_store import add_documents

    print(f"[Progress] Validating {len(files)} uploaded documents...")
    all_chunks = []
    processed_names = []
    
    settings.ensure_directories()
    
    for file in files:
        if not file.filename:
            continue
            
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Only PDF files are supported. Received: '{file.filename}'.",
            )
            
        doc_name = file.filename
        upload_path = Path(settings.upload_dir) / doc_name
        
        try:
            with open(upload_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            logger.info("Saved upload to: %s", upload_path)
        except Exception as exc:
            logger.error("Failed to save upload: %s", exc)
            raise HTTPException(status_code=500, detail=f"File save failed: {exc}")
            
        try:
            pages = parse_pdf(upload_path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"PDF parsing failed for {doc_name}: {exc}")
            
        if not pages:
            continue
            
        try:
            chunks = chunk_document(pages, document_name=doc_name)
            if chunks:
                all_chunks.extend(chunks)
                processed_names.append(doc_name)
        except Exception as exc:
            logger.error("Chunking failed for %s: %s", doc_name, exc)
            raise HTTPException(status_code=500, detail=f"Chunking failed for {doc_name}: {exc}")

    if not all_chunks:
        raise HTTPException(
            status_code=422,
            detail="Documents produced no usable text chunks.",
        )

    print(f"[Progress] Embedding and storing {len(all_chunks)} chunks from {len(processed_names)} files...")
    
    batch_size = 50
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        success = False
        rotated_this_batch = False
        while not success:
            try:
                add_documents(batch)
                success = True
                time.sleep(1.5)  # Pace the requests to avoid bursting
            except Exception as exc:
                err_str = str(exc).upper()
                is_recoverable = any(code in err_str for code in ["429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND", "403", "UNAUTHENTICATED", "INVALID_ARGUMENT"])
                
                if is_recoverable:
                    logger.warning(f"API Error at batch {i}: {exc}")
                    if not rotated_this_batch and rotate_key():
                        logger.warning(f"API key rotated successfully. Retrying immediately...")
                        rotated_this_batch = True
                        time.sleep(2)
                    else:
                        logger.warning(f"All keys exhausted. Sleeping for 180 seconds before retrying...")
                        time.sleep(180)
                        rotated_this_batch = False # Reset so we can try rotating again after the 180s cooldown
                else:
                    logger.error("Embedding/storage failed with fatal error: %s", exc)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Vector store ingestion failed: {exc}",
                    )


    # ── Rebuild BM25 ────────────────────────────────────────────────────
    print(f"[Progress] Rebuilding BM25 index...")
    try:
        rebuild_bm25_from_vector_store()
    except Exception as exc:
        # Non-fatal: dense search still works without BM25.
        logger.warning("BM25 rebuild failed (non-fatal): %s", exc)

    return IngestionResponse(
        status="success",
        document_names=processed_names,
        total_chunks=len(all_chunks),
        message=(
            f"Successfully ingested {len(processed_names)} documents → "
            f"{len(all_chunks)} chunks embedded and indexed."
        ),
    )

# ═══════════════════════════════════════════════════════════════════════════
# Ephemeral Document Extraction
# ═══════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/extract",
    tags=["Extraction"],
    summary="Extract raw text from a document for ephemeral context",
)
def extract_document(
    file: UploadFile = File(...),
) -> dict:
    """
    Parses a PDF or DOCX file and returns the raw text without saving
    it to the RAG database.
    """
    from ingestion.docx_parser import parse_docx
    from ingestion.parser import parse_pdf

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
        
    ext = file.filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")
        
    upload_path = Path(settings.upload_dir) / file.filename
    try:
        settings.ensure_directories()
        with open(upload_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"File save failed: {exc}")
        
    try:
        if ext == "pdf":
            pages = parse_pdf(upload_path)
        else:
            pages = parse_docx(upload_path)
            
        full_text = "\n\n".join([p["text"] for p in pages])
        
        # Clean up ephemeral file
        upload_path.unlink(missing_ok=True)
        
        return {"status": "success", "filename": file.filename, "text": full_text}
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# Legal Analysis (Chat Endpoint)
# ═══════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/analyze",
    response_model=AnalysisResponse,
    tags=["Analysis"],
    summary="Ask the AI Legal Advisor a question",
)
async def analyze(
    request: AnalysisRequest,
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
) -> AnalysisResponse:
    """
    Submit a legal question and receive a structured, grounded analysis.

    The pipeline:
      1. Hybrid retrieval (dense vector + BM25 keyword search).
      2. Cross-encoder reranking (Cohere Rerank → top 5 chunks).
      3. LLM generation with strict system prompt and source-attributed
         context.

    The response includes:
      - Structured analysis (Plain English Summary, Key Findings,
        Scenarios & Outcomes, Strategic Recommendations).
      - Ranked source chunks with document/section attribution.
      - Processing time metrics.
    """
    # ── Preflight check ─────────────────────────────────────────────────
    from llm.chain import run_analysis_pipeline
    from retrieval.vector_store import get_document_count

    global _health_documents_indexed, _health_vector_store_ready
    doc_count = get_document_count()
    _health_documents_indexed = doc_count
    _health_vector_store_ready = True
    if doc_count == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "No documents have been ingested yet. Please upload at least "
                "one legal document via POST /api/ingest before querying."
            ),
        )

    # Save user message to DB if chat_id is provided
    if request.chat_id:
        # Check if chat exists and belongs to the user
        chat_session = db.query(db_models.ChatSession).filter(
            db_models.ChatSession.id == request.chat_id,
            db_models.ChatSession.user_email == user_email
        ).first()
        if chat_session:
            user_msg = db_models.ChatMessage(
                session_id=request.chat_id,
                role="user",
                content=request.query
            )
            db.add(user_msg)
            
            # Update chat title if it's "New Chat"
            if chat_session.title == "New Chat":
                chat_session.title = request.query[:30] + ("..." if len(request.query) > 30 else "")
            
            db.commit()

    # ── Run the full RAG pipeline ───────────────────────────────────────
    print(f"[Progress] Running analysis pipeline for query: '{request.query}'...")
    try:
        response = await run_analysis_pipeline(
            query=request.query,
            document_filter=request.document_filter,
            top_k=request.top_k,
            model_preference=request.model_preference,
            ephemeral_context=request.ephemeral_context,
        )
    except RuntimeError as exc:
        logger.error("Analysis pipeline failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error in analysis pipeline: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {exc}",
        )

    # Save assistant message to DB
    if request.chat_id:
        chat_session = db.query(db_models.ChatSession).filter(
            db_models.ChatSession.id == request.chat_id,
            db_models.ChatSession.user_email == user_email
        ).first()
        if chat_session:
            structured_json = response.analysis.model_dump_json()
            sources_json = json.dumps([s.model_dump() for s in response.sources])
            
            assistant_msg = db_models.ChatMessage(
                session_id=request.chat_id,
                role="assistant",
                content="", # We use structured_content instead
                structured_content=structured_json,
                sources=sources_json
            )
            db.add(assistant_msg)
            chat_session.updated_at = db_models.datetime.utcnow()
            db.commit()

    return response


# ═══════════════════════════════════════════════════════════════════════════
# Document Management
# ═══════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/documents",
    tags=["Documents"],
    summary="List all ingested documents",
)
def list_documents() -> dict:
    """
    Return a list of all unique document names currently in the index,
    along with per-document chunk counts.
    """
    from retrieval.vector_store import get_vector_store

    try:
        store = get_vector_store()
        collection = store._collection

        doc_counts: dict[str, int] = {}
        offset = 0
        limit = 1000

        while True:
            batch = collection.get(include=["metadatas"], limit=limit, offset=offset)
            metadatas = batch.get("metadatas")
            if not metadatas:
                break

            for meta in metadatas:
                name = meta.get("document_name", "Unknown")
                doc_counts[name] = doc_counts.get(name, 0) + 1

            if len(metadatas) < limit:
                break
                
            offset += limit

        return {
            "total_documents": len(doc_counts),
            "total_chunks": sum(doc_counts.values()),
            "documents": [
                {"document_name": name, "chunk_count": count}
                for name, count in sorted(doc_counts.items())
            ],
        }
    except Exception as exc:
        logger.error("Failed to list documents: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete(
    "/api/documents",
    tags=["Documents"],
    summary="Delete a specific document from the index",
)
def remove_document(
    document_name: str = Query(
        ...,
        description="The exact document_name to remove from the index.",
    )
) -> dict:
    """
    Remove all chunks belonging to a specific document and rebuild the
    BM25 index.
    """
    from retrieval.bm25_retriever import rebuild_bm25_from_vector_store
    from retrieval.vector_store import delete_document

    deleted_count = delete_document(document_name)

    if deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for document '{document_name}'.",
        )

    # Rebuild BM25 after deletion.
    try:
        rebuild_bm25_from_vector_store()
    except Exception as exc:
        logger.warning("BM25 rebuild after deletion failed (non-fatal): %s", exc)

    return {
        "status": "success",
        "document_name": document_name,
        "chunks_deleted": deleted_count,
        "message": f"Deleted {deleted_count} chunks for '{document_name}'.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Error Handlers
# ═══════════════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch-all handler to prevent stack traces from leaking to clients."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please try again later.",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# Direct Execution
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )

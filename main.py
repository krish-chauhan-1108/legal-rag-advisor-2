"""
Legal RAG Advisor — FastAPI Application
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
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

print("[Progress] Loading config and settings...")
from config import settings

print("[Progress] Loading chunking module (Spacy/NLTK might load here)...")
from ingestion.chunker import chunk_document

print("[Progress] Loading DOCX parser...")
from ingestion.docx_parser import parse_docx

print("[Progress] Loading PDF parser...")
from ingestion.parser import parse_pdf

print("[Progress] Loading LLM chain (Transformers/SentenceTransformers might load here)...")
from llm.chain import run_analysis_pipeline

print("[Progress] Loading schemas...")
from models.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    HealthResponse,
    IngestionResponse,
)
from retrieval.bm25_retriever import rebuild_bm25_from_vector_store

print("[Progress] Loading Vector Store dependencies...")
from retrieval.vector_store import (
    add_documents,
    delete_document,
    get_document_count,
    get_vector_store,
    rotate_api_key,
)

print("[Progress] Loading Logger...")
from utils.logger import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Application Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown lifecycle manager.

    On startup:
      - Ensure required directories exist.
      - Initialize the vector store.
      - Rebuild the BM25 index from any previously persisted documents.

    On shutdown:
      - Log a clean shutdown message.
    """
    logger.info("=" * 60)
    logger.info("  Legal RAG Advisor — Starting up")
    logger.info("=" * 60)

    # Ensure data directories exist.
    print("[Progress] Ensuring data directories exist...")
    settings.ensure_directories()
    print("[Progress] Ensuring STATIC_DIR exists...")
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    print("[Progress] Rebuilding BM25 index on startup...")
    try:
        rebuild_bm25_from_vector_store()
    except Exception as exc:
        logger.error(f"Failed to rebuild BM25 index on startup: {exc}")

    print("[Progress] Application startup logic complete.")
    logger.info("Startup complete. Server ready on http://%s:%d", settings.host, settings.port)
    logger.info("=" * 60)

    yield  # ← Application runs here.

    logger.info("Legal RAG Advisor — Shutting down gracefully.")


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Legal RAG Advisor",
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
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve the frontend SPA ──────────────────────────────────────────────────
STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the single-page web UI at the root URL."""
    return FileResponse(STATIC_DIR / "index.html")


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
    Return the health status of the Legal RAG Advisor.

    Includes the number of indexed document chunks and whether the vector
    store is operational.
    """
    try:
        count = get_document_count()
        vs_ready = True
    except Exception:
        count = 0
        vs_ready = False

    return HealthResponse(
        status="healthy" if vs_ready else "degraded",
        documents_indexed=count,
        vector_store_ready=vs_ready,
    )


# ═══════════════════════════════════════════════════════════════════════════
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
                    if not rotated_this_batch and rotate_api_key():
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
    request: AnalysisRequest
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
    doc_count = get_document_count()
    if doc_count == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "No documents have been ingested yet. Please upload at least "
                "one legal document via POST /api/ingest before querying."
            ),
        )

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
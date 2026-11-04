import hashlib
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.integrations.vector_store import delete_document, list_documents
from app.schemas.rag import (
    DocumentIndexResponse,
    RAGAnswerResponse,
    RAGDocumentSummary,
    RAGQuestionRequest,
)
from app.services.rag.answering import answer_with_rag
from app.services.rag.documents import (
    MAX_DOCUMENT_SIZE,
    SUPPORTED_EXTENSIONS,
    index_document,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/rag", tags=["AI RAG"])


@router.get("/documents", response_model=list[RAGDocumentSummary])
async def get_rag_documents():
    """List unique indexed RAG documents."""
    return await run_in_threadpool(list_documents)


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rag_document(doc_id: str):
    """Delete all indexed chunks for a document."""
    deleted = await run_in_threadpool(delete_document, doc_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RAG document not found.",
        )
    return None


@router.post(
    "/documents",
    response_model=DocumentIndexResponse,
    status_code=status.HTTP_201_CREATED,
)
async def index_knowledge_document(
    file: Annotated[UploadFile, File(...)],
):
    """Upload a supported knowledge document and index it in ChromaDB."""
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()

    if not filename or extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Supported file types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    temp_path = None
    size = 0
    content_hash = hashlib.sha256()

    try:
        with tempfile.NamedTemporaryFile(
            suffix=extension,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        async with aiofiles.open(temp_path, "wb") as temp_file:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_DOCUMENT_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Document exceeds the maximum allowed size.",
                    )
                content_hash.update(chunk)
                await temp_file.write(chunk)

        if size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded document is empty.",
            )

        result = await run_in_threadpool(
            index_document,
            temp_path,
            filename,
            content_hash.hexdigest(),
            datetime.now(timezone.utc).isoformat(),
        )
        return DocumentIndexResponse(
            filename=filename,
            chunks_created=int(result["chunks_created"]),
            message="Document indexed successfully."
            if result["chunks_created"]
            else "No text chunks were found in the document.",
        )
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to index RAG document")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Document indexing failed. Check embedding configuration and server logs.",
        ) from exc
    finally:
        await file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.post("/ask", response_model=RAGAnswerResponse)
async def ask_knowledge_base(request: RAGQuestionRequest):
    """Answer a question using relevant documents retrieved from ChromaDB."""
    try:
        result = await answer_with_rag(request.question, k=request.k)
        return RAGAnswerResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG question answering failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to answer the question. Check Gemini and ChromaDB configuration.",
        ) from exc

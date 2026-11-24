from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    get_analytics_service,
    get_current_user_id,
    get_rag_document_repository,
)
from app.core.config import get_settings
from app.integrations.gemini_key_pool import AllKeysExhausted
from app.integrations.llm import LLMNotConfiguredError
from app.integrations.vector_store import (
    delete_document,
    document_vectors_are_current,
    mark_document_vectors_stale,
)
from app.repositories.rag_documents import RAGDocumentRepository
from app.schemas.rag import (
    DocumentIndexResponse,
    RAGAnswerResponse,
    RAGDocumentSummary,
    RAGQuestionRequest,
)
from app.services.analytics import AnalyticsService
from app.services.rag.answering import answer_with_rag
from app.services.rag.documents import (
    MAX_DOCUMENT_SIZE,
    SUPPORTED_EXTENSIONS,
    content_hash,
    index_parsed_document,
    normalize_filename,
    prepare_document,
    stable_document_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/rag", tags=["AI RAG"])


@router.get(
    "/documents",
    response_model=list[RAGDocumentSummary],
)
async def get_rag_documents(
    user_id: str = Depends(get_current_user_id),
    repository: RAGDocumentRepository = Depends(get_rag_document_repository),
):
    documents = await repository.list_for_user(user_id)
    return [
        {
            "doc_id": str(document.get("doc_id") or document.get("document_id") or ""),
            "source": str(document.get("source") or document.get("original_filename") or "Knowledge base"),
            "chunk_count": int(document.get("chunk_count") or document.get("chunks_created") or 0),
            "vector_index_status": str(
                document.get("status") or document.get("vector_index_status") or "pending"
            ),
        }
        for document in documents
    ]


@router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_rag_document(
    doc_id: str,
    user_id: str = Depends(get_current_user_id),
    repository: RAGDocumentRepository = Depends(get_rag_document_repository),
):
    if not doc_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document ID cannot be empty.",
        )

    source = await repository.get(user_id=user_id, doc_id=doc_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RAG document not found.",
        )

    try:
        await run_in_threadpool(delete_document, doc_id, user_id)
        if not await repository.delete(user_id=user_id, doc_id=doc_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="RAG document not found.",
            )
    except HTTPException:
        raise
    except AllKeysExhausted:
        raise
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured.",
        ) from exc
    except Exception as exc:
        logger.warning(
            "Failed to delete RAG document",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to delete the indexed document.",
        ) from exc

    return None


@router.post(
    "/documents",
    response_model=DocumentIndexResponse,
    status_code=status.HTTP_201_CREATED,
)
async def index_knowledge_document(
    file: Annotated[UploadFile, File(...)],
    user_id: str = Depends(get_current_user_id),
    repository: RAGDocumentRepository = Depends(get_rag_document_repository),
):
    raw_filename = file.filename or ""
    filename = Path(raw_filename.replace("\\", "/")).name
    extension = Path(filename).suffix.lower()
    if (
        not filename
        or filename in {".", ".."}
        or extension not in SUPPORTED_EXTENSIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported file type. Supported types: "
                f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    try:
        content = await file.read(MAX_DOCUMENT_SIZE + 1)
        if len(content) > MAX_DOCUMENT_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Document exceeds the maximum allowed size of 10 MB.",
            )
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded document is empty.",
            )

        chunks = await run_in_threadpool(prepare_document, filename, content)
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No text or table rows were found in the document.",
            )

        uploaded_at = datetime.now(timezone.utc).isoformat()
        document_hash = content_hash(content)
        doc_id = stable_document_id(filename)
        normalized = normalize_filename(filename)

        # Duplicate prevention: check if identical document is already indexed and current
        existing_doc = await repository.get(user_id=user_id, doc_id=doc_id)
        if (
            existing_doc is not None
            and existing_doc.get("content_hash") == document_hash
            and (existing_doc.get("status") == "completed" or existing_doc.get("vector_index_status") == "completed")
        ):
            is_current = await run_in_threadpool(
                document_vectors_are_current, doc_id, user_id, document_hash
            )
            if is_current:
                chunk_count = int(existing_doc.get("chunk_count") or existing_doc.get("chunks_created") or 0)
                return DocumentIndexResponse(
                    doc_id=doc_id,
                    filename=filename,
                    chunks_created=chunk_count,
                    message="Document is already indexed and up-to-date in ChromaDB.",
                )

        collection_name = get_settings().chroma_collection_name
        await repository.upsert_source(
            {
                "user_id": user_id,
                "doc_id": doc_id,
                "document_id": doc_id,
                "normalized_filename": normalized,
                "source": filename,
                "original_filename": filename,
                "file_type": extension.lstrip("."),
                "raw_content": content,
                "content_hash": document_hash,
                "uploaded_at": uploaded_at,
                "status": "processing",
                "vector_index_status": "processing",
                "embedding_model": get_settings().gemini_embedding_model,
                "collection_name": collection_name,
                "chroma_collection": collection_name,
                "chunks_created": 0,
                "chunk_count": 0,
            }
        )

        try:
            await run_in_threadpool(mark_document_vectors_stale, doc_id, user_id)

            result = await run_in_threadpool(
                index_parsed_document,
                chunks,
                user_id=user_id,
                source_filename=filename,
                doc_id=doc_id,
                content_hash_value=document_hash,
                uploaded_at=uploaded_at,
            )
            chunks_created = int(result["chunks_created"])
            await repository.mark_indexed(
                user_id=user_id,
                doc_id=doc_id,
                content_hash=document_hash,
                indexed_at=datetime.now(timezone.utc).isoformat(),
                embedding_model=get_settings().gemini_embedding_model,
                chunks_created=chunks_created,
                collection_name=collection_name,
            )
            return DocumentIndexResponse(
                doc_id=doc_id,
                filename=filename,
                chunks_created=chunks_created,
                message="Document indexed successfully in ChromaDB.",
            )
        except Exception as exc:
            logger.warning(
                "Document indexing failed for doc_id=%s: %s", doc_id, exc, exc_info=True
            )
            try:
                await run_in_threadpool(delete_document, doc_id, user_id)
            except Exception as clean_exc:
                logger.warning("Cleanup of partial vectors failed: %s", clean_exc)
            await repository.mark_failed(
                user_id=user_id,
                doc_id=doc_id,
                error_message=str(exc),
            )
            raise

    except HTTPException:
        raise
    except AllKeysExhausted:
        raise
    except LLMNotConfiguredError as exc:
        logger.warning("Gemini configuration is missing for RAG document indexing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.warning(
            "Failed to index uploaded RAG document",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Document indexing failed. Check embedding configuration.",
        ) from exc
    finally:
        await file.close()


@router.post(
    "/ask",
    response_model=RAGAnswerResponse,
)
async def ask_knowledge_base(
    request: RAGQuestionRequest,
    user_id: str = Depends(get_current_user_id),
    analytics: AnalyticsService = Depends(get_analytics_service),
):
    question = request.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty.",
        )

    try:
        result = await answer_with_rag(
            question=question,
            k=request.k,
            user_id=user_id,
            analytics=analytics,
            history=[item.model_dump() for item in request.history],
            source_type=request.source_type,
            start_date=request.start_date,
            end_date=request.end_date,
        )
        return RAGAnswerResponse.model_validate(result)
    except AllKeysExhausted:
        raise
    except LLMNotConfiguredError as exc:
        logger.warning("Gemini configuration is missing for RAG answering")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.warning(
            "RAG question answering failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to answer the question. Check Gemini and ChromaDB configuration.",
        ) from exc

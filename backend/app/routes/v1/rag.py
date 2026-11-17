<<<<<<< HEAD:backend/app/routes/v1/rag.py
import logging
import aiofiles
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ...schemas.rag import (
=======
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
from app.integrations.vector_store import delete_document, mark_document_vectors_stale
from app.repositories.rag_documents import RAGDocumentRepository
from app.schemas.rag import (
>>>>>>> 3d11468 (updated the some backend and frontend files):backend/app/api/v1/endpoints/rag.py
    DocumentIndexResponse,
    RAGAnswerResponse,
    RAGQuestionRequest,
)
<<<<<<< HEAD:backend/app/routes/v1/rag.py
from ...services.ai_service import answer_with_rag
from ...services.document_service import (
=======
from app.services.analytics import AnalyticsService
from app.services.rag.answering import answer_with_rag
from app.services.rag.documents import (
>>>>>>> 3d11468 (updated the some backend and frontend files):backend/app/api/v1/endpoints/rag.py
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


<<<<<<< HEAD:backend/app/routes/v1/rag.py
=======
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
            "doc_id": str(document["doc_id"]),
            "source": str(document.get("source", "Knowledge base")),
            "chunk_count": int(document.get("chunks_created", 0)),
            "vector_index_status": str(
                document.get("vector_index_status", "pending")
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


>>>>>>> 3d11468 (updated the some backend and frontend files):backend/app/api/v1/endpoints/rag.py
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

<<<<<<< HEAD:backend/app/routes/v1/rag.py
    temp_path = None
    size = 0

    try:
        async with aiofiles.open("temp_file", "wb") as temp_file:
            temp_path = Path(str(temp_file.name))
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
                await temp_file.write(chunk)

        if size == 0:
=======
    try:
        content = await file.read(MAX_DOCUMENT_SIZE + 1)
        if len(content) > MAX_DOCUMENT_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Document exceeds the maximum allowed size of 10 MB.",
            )
        if not content:
>>>>>>> 3d11468 (updated the some backend and frontend files):backend/app/api/v1/endpoints/rag.py
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded document is empty.",
            )

<<<<<<< HEAD:backend/app/routes/v1/rag.py
        result = await run_in_threadpool(index_document, temp_path)
=======
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
        await repository.upsert_source(
            {
                "user_id": user_id,
                "doc_id": doc_id,
                "normalized_filename": normalized,
                "source": filename,
                "file_type": extension.lstrip("."),
                "raw_content": content,
                "content_hash": document_hash,
                "uploaded_at": uploaded_at,
                "vector_index_status": "pending",
                "embedding_model": get_settings().gemini_embedding_model,
            }
        )

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
        )
>>>>>>> 3d11468 (updated the some backend and frontend files):backend/app/api/v1/endpoints/rag.py
        return DocumentIndexResponse(
            doc_id=doc_id,
            filename=filename,
<<<<<<< HEAD:backend/app/routes/v1/rag.py
            chunks_created=int(result["chunks_created"]),
            message="Document indexed successfully." if result["chunks_created"] else "No text chunks were found in the document.",
=======
            chunks_created=chunks_created,
            message="Document indexed successfully in ChromaDB.",
>>>>>>> 3d11468 (updated the some backend and frontend files):backend/app/api/v1/endpoints/rag.py
        )

    except HTTPException:
        raise
<<<<<<< HEAD:backend/app/routes/v1/rag.py
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
=======
    except AllKeysExhausted:
        raise
    except LLMNotConfiguredError as exc:
        logger.warning("Gemini configuration is missing for RAG document indexing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured.",
        ) from exc
>>>>>>> 3d11468 (updated the some backend and frontend files):backend/app/api/v1/endpoints/rag.py
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

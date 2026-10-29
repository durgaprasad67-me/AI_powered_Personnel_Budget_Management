import logging
import aiofiles
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ...schemas.rag import (
    DocumentIndexResponse,
    RAGAnswerResponse,
    RAGQuestionRequest,
)
from ...services.ai_service import answer_with_rag
from ...services.document_service import (
    MAX_DOCUMENT_SIZE,
    SUPPORTED_EXTENSIONS,
    index_document,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/rag", tags=["AI RAG"])


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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded document is empty.",
            )

        result = await run_in_threadpool(index_document, temp_path)
        return DocumentIndexResponse(
            filename=filename,
            chunks_created=int(result["chunks_created"]),
            message="Document indexed successfully." if result["chunks_created"] else "No text chunks were found in the document.",
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

import asyncio
from pathlib import Path
import sys

backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

from app.core.config import get_settings
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.db.client import get_database
from app.db.collections import RAG_DOCUMENTS
from app.repositories.rag_documents import RAGDocumentRepository
from app.services.rag import documents

async def index_docs():
    user_id = DEFAULT_CURRENT_USER_ID
    db = get_database()
    repo = RAGDocumentRepository(db[RAG_DOCUMENTS])
    
    files_to_index = [
        "Transactions_Unique_PDF.pdf",
        "Transactions_Unique_DOCX.docx",
        "Transactions_Unique_TXT.txt",
    ]
    
    data_dir = Path("data")
    for fname in files_to_index:
        fpath = data_dir / fname
        if not fpath.exists():
            print(f"File {fpath} does not exist!")
            continue
            
        content = fpath.read_bytes()
        chunks = documents.prepare_document(fname, content)
        doc_id = documents.stable_document_id(fname)
        chash = documents.content_hash(content)
        uploaded_at = "2026-11-24T12:00:00Z"
        
        print(f"Indexing {fname}: {len(chunks)} chunks, doc_id={doc_id}...")
        res = documents.index_parsed_document(
            chunks,
            user_id=user_id,
            source_filename=fname,
            doc_id=doc_id,
            content_hash_value=chash,
            uploaded_at=uploaded_at,
        )
        print(f"  Chroma indexed: {res}")
        
        await repo.upsert_source({
            "user_id": user_id,
            "doc_id": doc_id,
            "document_id": doc_id,
            "normalized_filename": documents.normalize_filename(fname),
            "source": fname,
            "original_filename": fname,
            "file_type": Path(fname).suffix.lstrip("."),
            "raw_content": content,
            "content_hash": chash,
            "uploaded_at": uploaded_at,
            "status": "completed",
            "vector_index_status": "completed",
            "embedding_model": get_settings().gemini_embedding_model,
            "collection_name": get_settings().chroma_collection_name,
            "chroma_collection": get_settings().chroma_collection_name,
            "chunks_created": res["chunks_created"],
            "chunk_count": res["chunks_created"],
        })
        print(f"  MongoDB cataloged.")

if __name__ == "__main__":
    asyncio.run(index_docs())

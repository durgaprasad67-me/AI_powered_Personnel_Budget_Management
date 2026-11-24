import asyncio
import json
from pathlib import Path
import sys

backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

from app.core.config import get_settings
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.db.client import get_database
from app.db.collections import RAG_DOCUMENTS, TRANSACTIONS
import chromadb
from app.integrations.vector_store import _raw_collection

async def inspect():
    settings = get_settings()
    print("=== ChromaDB Settings ===")
    print("Persist dir:", settings.chroma_persist_directory)
    print("Active collection:", settings.chroma_collection_name)
    print("Default User ID:", DEFAULT_CURRENT_USER_ID)
    
    client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
    if client:
        cols = client.list_collections()
        print("Available collections:", [c.name for c in cols])
        for c in cols:
            print(f"\n--- Collection '{c.name}' (count={c.count()}, meta={c.metadata}) ---")
            data = c.get(include=["metadatas", "documents"])
            for cid, meta, doc in zip(data["ids"][:15], data["metadatas"][:15], data["documents"][:15]):
                print(f"  ID: {cid}")
                print(f"    Meta: {meta}")
                print(f"    Text: {repr(doc[:120])}")
            if c.count() > 15:
                print(f"    ... and {c.count() - 15} more items")
                
    db = get_database()
    doc_col = db[RAG_DOCUMENTS]
    docs = await doc_col.find().to_list(100)
    print(f"\n=== MongoDB rag_documents (count={len(docs)}) ===")
    for d in docs:
        print(f"  doc_id: {d.get('doc_id')} | user_id: {d.get('user_id')} | source: {d.get('source')} | chunks: {d.get('chunk_count') or d.get('chunks_created')} | status: {d.get('status')}")

    tx_col = db[TRANSACTIONS]
    tx_count = await tx_col.count_documents({})
    print(f"\n=== MongoDB transactions (count={tx_count}) ===")
    sample_txs = await tx_col.find().to_list(5)
    for t in sample_txs:
        print(f"  TX: {t.get('_id')} | user_id: {t.get('user_id')} | desc: {t.get('description') or t.get('merchant')} | amount: {t.get('amount')} | date: {t.get('date')}")

if __name__ == "__main__":
    asyncio.run(inspect())


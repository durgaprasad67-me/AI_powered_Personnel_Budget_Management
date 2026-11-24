import asyncio
import chromadb
from pathlib import Path
import sys

sys.path.insert(0, "backend")
from app.core.config import get_settings
from app.db.collections import RAG_DOCUMENTS
from pymongo.asynchronous.mongo_client import AsyncMongoClient

async def main():
    settings = get_settings()
    print("--- 1. CHROMADB INSPECTION ---")
    client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
    for c in client.list_collections():
        print(f"\nCollection: {c.name} (count={c.count()})")
        data = c.get(include=["metadatas", "documents"])
        for idx, (cid, doc, meta) in enumerate(zip(data.get("ids", []), data.get("documents", []), data.get("metadatas", []))):
            print(f"  [{idx}] ID: {cid}")
            print(f"      Source: {meta.get('source')} | Type: {meta.get('source_type')} | User: {meta.get('user_id')} | ChunkIdx: {meta.get('chunk_index')}")
            print(f"      DocID: {meta.get('doc_id')} | State: {meta.get('vector_state')} | ContentHash: {meta.get('content_hash')}")
            print(f"      Text: {repr(doc[:75])}")

    print("\n--- 2. MONGODB RAG_DOCUMENTS INSPECTION ---")
    from app.db.client import get_database, close_database
    db = get_database()
    count = await db[RAG_DOCUMENTS].count_documents({})
    print(f"Total documents in {RAG_DOCUMENTS}: {count}")
    async for d in db[RAG_DOCUMENTS].find({}):
        raw_len = len(d.get("raw_content", b"")) if d.get("raw_content") else 0
        d_summary = {k: v for k, v in d.items() if k != "raw_content"}
        d_summary["raw_content_bytes"] = raw_len
        print(f"  Doc: {d_summary}")
    await close_database()

if __name__ == "__main__":
    asyncio.run(main())

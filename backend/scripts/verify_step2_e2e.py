import asyncio
import io
from pathlib import Path
import sys
from unittest.mock import patch
import httpx

sys.path.insert(0, "backend")

from app.core.config import get_settings
from app.db.client import get_database, close_database
from app.db.collections import RAG_DOCUMENTS
from app.integrations.vector_store import get_vector_store
from app.main import app

TEST_USER = "step2_verify_user"

async def run_step2_verification():
    print("=" * 60)
    print("STEP 2 E2E VERIFICATION TEST SUITE")
    print("=" * 60)

    settings = get_settings()
    db = get_database()
    store = get_vector_store()
    raw_col = store._collection

    # 0. Initial Clean-up for test user
    print("\n[Step 0] Cleaning test artifacts for user:", TEST_USER)
    await db[RAG_DOCUMENTS].delete_many({"user_id": TEST_USER})
    test_chunks = raw_col.get(where={"user_id": TEST_USER})
    if test_chunks.get("ids"):
        raw_col.delete(ids=test_chunks["ids"])
    print("Test environment clean.")

    # Check existing collections state
    print(f"Active collection '{settings.chroma_collection_name}' chunk count: {raw_col.count()}")
    import chromadb
    chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
    legacy_col = chroma_client.get_collection("finsight_knowledge_legacy_3072")
    print(f"Legacy collection 'finsight_knowledge_legacy_3072' chunk count: {legacy_col.count()}")
    mongo_docs_before = await db[RAG_DOCUMENTS].count_documents({})
    print(f"MongoDB '{RAG_DOCUMENTS}' document count before: {mongo_docs_before}")

    # Transport for FastAPI ASGI app
    transport = httpx.ASGITransport(app=app)
    headers = {"X-User-Id": TEST_USER}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client_http:
        # 1. Upload existing supported document (data/budget-guide.txt)
        print("\n--- TEST 1: Upload Existing Supported Document ---")
        doc_path = Path("data/budget-guide.txt")
        assert doc_path.exists(), f"Source file not found: {doc_path}"
        content = doc_path.read_bytes()

        files = {"file": ("budget-guide.txt", io.BytesIO(content), "text/plain")}
        res = await client_http.post("/api/v1/ai/rag/documents", files=files, headers=headers)
        print("Upload Response Status:", res.status_code)
        print("Upload Response JSON:", res.json())
        assert res.status_code in (200, 201), f"Upload failed: {res.text}"
        data = res.json()
        doc_id = data["doc_id"]
        chunks_created = data["chunks_created"]
        assert chunks_created > 0, "No chunks created!"
        print(f"TEST 1 PASS: Upload succeeded. doc_id={doc_id}, chunks_created={chunks_created}")

        # 2. Verify chunks in ChromaDB
        print("\n--- TEST 2: Verify Chunks in ChromaDB ---")
        chroma_res = raw_col.get(where={"user_id": TEST_USER}, include=["metadatas", "documents"])
        retrieved_ids = chroma_res.get("ids", [])
        retrieved_metas = chroma_res.get("metadatas", [])
        print(f"ChromaDB chunks found for {TEST_USER}: {len(retrieved_ids)}")
        assert len(retrieved_ids) == chunks_created, f"Expected {chunks_created} chunks, got {len(retrieved_ids)}"
        for idx, (cid, meta) in enumerate(zip(retrieved_ids, retrieved_metas)):
            print(f"  Chunk {idx}: ID={cid}")
            print(f"    Metadata: {meta}")
            assert meta.get("user_id") == TEST_USER, "user_id mismatch"
            assert meta.get("doc_id") == doc_id or meta.get("document_id") == doc_id, "doc_id mismatch"
            assert meta.get("source") == "budget-guide.txt", "source mismatch"
            assert meta.get("chunk_index") == idx, "chunk_index mismatch"
            assert meta.get("vector_state") == "indexed", "vector_state mismatch"
            assert meta.get("collection_name") == settings.chroma_collection_name, "collection_name mismatch"
        print("TEST 2 PASS: All chunk metadata verified in ChromaDB.")

        # 3. Verify document record in MongoDB
        print("\n--- TEST 3: Verify Document Record in MongoDB ---")
        mongo_doc = await db[RAG_DOCUMENTS].find_one({"user_id": TEST_USER, "doc_id": doc_id})
        assert mongo_doc is not None, "MongoDB document record not found!"
        print("MongoDB Record found:")
        for k, v in mongo_doc.items():
            if k != "raw_content":
                print(f"  {k}: {v}")
        assert mongo_doc.get("status") == "completed", f"Expected status completed, got {mongo_doc.get('status')}"
        assert mongo_doc.get("vector_index_status") == "completed", f"Expected vector_index_status completed, got {mongo_doc.get('vector_index_status')}"
        assert mongo_doc.get("chunk_count") == chunks_created, "chunk_count mismatch"
        assert mongo_doc.get("original_filename") == "budget-guide.txt", "original_filename mismatch"
        assert mongo_doc.get("file_type") == "txt", "file_type mismatch"
        assert mongo_doc.get("collection_name") == settings.chroma_collection_name, "collection_name mismatch"
        assert mongo_doc.get("uploaded_at") is not None, "uploaded_at missing"
        print("TEST 3 PASS: MongoDB record verified with full metadata and completed status.")

        # 4. Upload same document again & 5. Verify duplicates are NOT created
        print("\n--- TEST 4 & 5: Upload Same Document Again (Duplicate Prevention) ---")
        files_repeat = {"file": ("budget-guide.txt", io.BytesIO(content), "text/plain")}
        res_repeat = await client_http.post("/api/v1/ai/rag/documents", files=files_repeat, headers=headers)
        print("Repeat Upload Status:", res_repeat.status_code)
        print("Repeat Upload JSON:", res_repeat.json())
        assert res_repeat.status_code in (200, 201), f"Repeat upload failed: {res_repeat.text}"

        # Verify ChromaDB chunk count is STILL chunks_created (not doubled)
        chroma_res_after = raw_col.get(where={"user_id": TEST_USER})
        after_chunk_count = len(chroma_res_after.get("ids", []))
        print(f"ChromaDB chunk count after re-upload: {after_chunk_count} (original: {chunks_created})")
        assert after_chunk_count == chunks_created, f"Duplicates created! Found {after_chunk_count} chunks instead of {chunks_created}"

        # Verify MongoDB document count is STILL 1
        mongo_count_after = await db[RAG_DOCUMENTS].count_documents({"user_id": TEST_USER})
        print(f"MongoDB document count for user after re-upload: {mongo_count_after}")
        assert mongo_count_after == 1, f"MongoDB duplicate records created! Found {mongo_count_after}"
        print("TEST 4 & 5 PASS: Duplicate upload prevented cleanly. Zero duplicate chunks or records.")

        # 6. Verify failed indexing does not leave a false completed record
        print("\n--- TEST 6: Verify Failed Indexing Handling ---")
        fail_content = b"Content for failed indexing test."
        files_fail = {"file": ("failing_doc.txt", io.BytesIO(fail_content), "text/plain")}

        with patch("app.api.v1.endpoints.rag.index_parsed_document", side_effect=RuntimeError("Simulated embedding/indexing error")):
            res_fail = await client_http.post("/api/v1/ai/rag/documents", files=files_fail, headers=headers)
            print("Failed Upload HTTP Status:", res_fail.status_code)
            assert res_fail.status_code in (500, 502), f"Expected 500/502 error, got {res_fail.status_code}"

        failing_doc_record = await db[RAG_DOCUMENTS].find_one({"user_id": TEST_USER, "original_filename": "failing_doc.txt"})
        assert failing_doc_record is not None, "Failed document record should exist in MongoDB"
        print(f"Failed doc status in MongoDB: {failing_doc_record.get('status')}")
        print(f"Failed doc error_message: {failing_doc_record.get('error_message')}")
        assert failing_doc_record.get("status") == "failed", f"Expected status 'failed', got {failing_doc_record.get('status')}"
        assert failing_doc_record.get("vector_index_status") == "failed", "Expected vector_index_status 'failed'"

        # Verify no orphaned chunks in ChromaDB for failing doc
        fail_chunks = raw_col.get(where={"$and": [{"user_id": TEST_USER}, {"source": "failing_doc.txt"}]})
        assert len(fail_chunks.get("ids", [])) == 0, "Orphaned chunks found in ChromaDB after failure!"
        print("TEST 6 PASS: Failed indexing marked as 'failed', no false completed record, no orphaned Chroma chunks.")

        # Clean up the failed doc record before test 7
        await db[RAG_DOCUMENTS].delete_one({"user_id": TEST_USER, "original_filename": "failing_doc.txt"})

        # 7. Verify deletion removes only the selected document
        print("\n--- TEST 7: Verify Deletion Removes Only Selected Document ---")
        del_res = await client_http.delete(f"/api/v1/ai/rag/documents/{doc_id}", headers=headers)
        print("Delete Response Status:", del_res.status_code)
        assert del_res.status_code == 204, f"Delete failed: {del_res.status_code}"

        # Verify ChromaDB chunks removed for this doc
        chroma_after_del = raw_col.get(where={"user_id": TEST_USER})
        assert len(chroma_after_del.get("ids", [])) == 0, "Chroma chunks not deleted!"

        # Verify MongoDB record removed
        mongo_after_del = await db[RAG_DOCUMENTS].find_one({"user_id": TEST_USER, "doc_id": doc_id})
        assert mongo_after_del is None, "MongoDB record not deleted!"

        # Verify legacy collection untouched
        assert legacy_col.count() == 6, f"Legacy collection altered! Expected 6, got {legacy_col.count()}"
        print("TEST 7 PASS: Deletion cleanly removed only the selected document from ChromaDB and MongoDB.")

    # Final summary counts
    print("\n" + "=" * 60)
    final_mongo_count = await db[RAG_DOCUMENTS].count_documents({})
    final_chroma_count = raw_col.count()
    legacy_count = legacy_col.count()
    print("FINAL SUMMARY COUNTS:")
    print(f"  Active ChromaDB collection count: {final_chroma_count}")
    print(f"  Legacy ChromaDB collection count: {legacy_count}")
    print(f"  MongoDB '{RAG_DOCUMENTS}' count: {final_mongo_count}")
    print("ALL STEP 2 TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

    await close_database()

if __name__ == "__main__":
    asyncio.run(run_step2_verification())

import os
import sys
from pathlib import Path

# 1. Test from project root
print("--- TEST 1, 2, 3: Persistence Path Canonical Resolution ---")
root_dir = Path(__file__).resolve().parents[2]
backend_dir = root_dir / "backend"

# Import settings when CWD is project root
os.chdir(root_dir)
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings
settings_root = get_settings()
path_from_root = Path(settings_root.chroma_persist_directory).resolve()
print(f"Project root CWD ({os.getcwd()}): {path_from_root}")

# Switch CWD to backend directory and re-check
os.chdir(backend_dir)
settings_backend = get_settings()
path_from_backend = Path(settings_backend.chroma_persist_directory).resolve()
print(f"Backend CWD ({os.getcwd()}): {path_from_backend}")

expected_canonical_path = (backend_dir / "chroma_db").resolve()
assert path_from_root == expected_canonical_path, f"Path from root mismatch: {path_from_root} != {expected_canonical_path}"
assert path_from_backend == expected_canonical_path, f"Path from backend mismatch: {path_from_backend} != {expected_canonical_path}"
assert path_from_root == path_from_backend, "Root and Backend paths do not match!"
print("TEST 1-3 PASS: Both resolve to canonical path: " + str(expected_canonical_path))

# Tests 4, 5, 6, 7
print("\n--- TEST 4, 5, 6, 7: ChromaDB Collection Configuration & Validation ---")
from app.integrations.vector_store import get_vector_store, _configuration_space

# Test 7: get_vector_store() initializes without RuntimeError
print("Calling get_vector_store()...")
store = get_vector_store()
print("TEST 7 PASS: get_vector_store() initialized without RuntimeError!")

col = store._collection
print(f"Collection Name: {col.name}")
print(f"Chunk Count: {col.count()}")
print(f"Collection Metadata: {col.metadata}")

# Test 5: Verify collection metadata
assert col.metadata.get("embedding_model") == "gemini-embedding-001", f"Bad embedding_model: {col.metadata.get('embedding_model')}"
assert col.metadata.get("embedding_dim") == 768, f"Bad embedding_dim: {col.metadata.get('embedding_dim')}"
assert col.metadata.get("distance") == "cosine", f"Bad distance: {col.metadata.get('distance')}"
print("TEST 5 PASS: Collection metadata verified.")

# Test 6: Verify cosine distance configuration
hnsw_space = _configuration_space(col)
print(f"Collection HNSW space: {hnsw_space}")
assert hnsw_space == "cosine", f"Expected 'cosine' space, got '{hnsw_space}'"
print("TEST 6 PASS: Cosine distance configuration verified.")

# Test 4: Verify embedding dimensions
stored = col.get(limit=1, include=["embeddings"])
stored_embeddings = stored.get("embeddings")
if stored_embeddings is not None and len(stored_embeddings) > 0:
    stored_dim = len(stored_embeddings[0])
    print(f"Stored vector dimension: {stored_dim}")
    assert stored_dim == 768, f"Expected 768 stored vector dimension, got {stored_dim}"
else:
    print("Stored vector count: 0 (clean collection)")

embeddings_fn = store._embedding_function
probe = embeddings_fn.embed_query("FinSight AI validation probe")
print(f"Gemini probe dimension: {len(probe)}")
assert len(probe) == 768, f"Expected 768 probe dimension, got {len(probe)}"
print("TEST 4 PASS: Gemini probe verified at 768 dimensions.")

print("\nALL STEP 1 TESTS COMPLETED SUCCESSFULLY!")

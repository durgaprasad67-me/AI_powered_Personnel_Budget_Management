"""Step 5 Verification Script: Improve ChromaDB Retrieval Quality.

Tests the 12 audit questions against existing documents:
- Questions 1-3, 5, 8-10: retrieve relevant information.
- Questions 4, 6, 7: retrieve chunks containing actual answers.
- Questions 11, 12: must not invent answers (absent information).
- Tests duplicate chunk handling and prevents duplicates from crowding out unique chunks.

Records for every test:
- Query embedding generated: YES/NO
- Retrieved chunk IDs
- Retrieved source documents
- Relevance of retrieved chunks
- Duplicate chunks found
- Context passed to LLM
- Answer correctness
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from unittest.mock import patch

backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

from app.core.config import get_settings
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.integrations import vector_store
from app.services.rag import answering

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_step5")


AUDIT_QUESTIONS = [
    {
        "id": 1,
        "question": "How much was paid for hostel fee in February 2026?",
        "expected_facts": ["8,500", "8500", "Hostel fee"],
        "expected_source": "Transactions_Unique_DOCX.docx",
        "should_find": True,
    },
    {
        "id": 2,
        "question": "What was the amount received for the coding contest prize?",
        "expected_facts": ["5,000", "5000", "Coding contest prize"],
        "expected_source": "Transactions_Unique_DOCX.docx",
        "should_find": True,
    },
    {
        "id": 3,
        "question": "When was the dental appointment and how much did it cost?",
        "expected_facts": ["2,400", "2400", "Dental appointment", "August 19", "2026-08-19"],
        "expected_source": "Transactions_Unique_PDF.pdf",
        "should_find": True,
    },
    {
        "id": 4,
        "question": "What was the expense for the weekend resort booking?",
        "expected_facts": ["6,200", "6200", "Weekend resort booking"],
        "expected_source": "Transactions_Unique_PDF.pdf",
        "should_find": True,
    },
    {
        "id": 5,
        "question": "How much did I earn from freelance debugging work?",
        "expected_facts": ["4,200", "4200", "Freelance debugging"],
        "expected_source": "Transactions_Unique_DOCX.docx",
        "should_find": True,
    },
    {
        "id": 6,
        "question": "What was spent on buying athletic footwear?",
        "expected_facts": ["3,800", "3800", "Sports shoes"],
        "expected_source": "Transactions_Unique_PDF.pdf",
        "should_find": True,
    },
    {
        "id": 7,
        "question": "How much was the Cloud storage plan?",
        "expected_facts": ["299", "Cloud storage plan"],
        "expected_source": "Transactions_Unique_PDF.pdf",
        "should_find": True,
    },
    {
        "id": 8,
        "question": "What were the internship stipends received between May and September 2026?",
        "expected_facts": ["18,000", "18000", "19,000", "19000", "Internship stipend"],
        "expected_source": "Transactions_Unique_DOCX.docx",
        "should_find": True,
    },
    {
        "id": 9,
        "question": "What healthcare expenses are recorded in the PDF dataset?",
        "expected_facts": ["Pharmacy medicines", "1,120", "1120", "Dental appointment", "2,400", "2400"],
        "expected_source": "Transactions_Unique_PDF.pdf",
        "should_find": True,
    },
    {
        "id": 10,
        "question": "What was the fee paid for the placement course in August 2026?",
        "expected_facts": ["3,400", "3400", "Placement course"],
        "expected_source": "Transactions_Unique_DOCX.docx",
        "should_find": True,
    },
    {
        "id": 11,
        "question": "How much was spent on gym membership in the DOCX file?",
        "expected_facts": [],
        "expected_source": None,
        "should_find": False,
    },
    {
        "id": 12,
        "question": "What was the amount paid for car insurance in 2026?",
        "expected_facts": [],
        "expected_source": None,
        "should_find": False,
    },
]


async def run_audit():
    user_id = DEFAULT_CURRENT_USER_ID
    settings = get_settings()

    logger.info("=== STEP 5: RUNNING 12 RETRIEVAL QUALITY AUDIT QUESTIONS ===")
    logger.info("User ID: %s", user_id)
    logger.info("Chroma persist dir: %s", settings.chroma_persist_directory)
    logger.info("Chroma collection: %s", settings.chroma_collection_name)

    contexts_captured: list[dict[str, str]] = []
    original_generate_response = answering.generate_response

    async def tracking_generate_response(
        question: str,
        context: str = "",
        system_prompt: str = answering.DEFAULT_SYSTEM_PROMPT,
        history=None,
    ) -> str:
        contexts_captured.append({
            "question": question,
            "context": context,
            "system_prompt": system_prompt,
        })
        return await original_generate_response(
            question=question,
            context=context,
            system_prompt=system_prompt,
            history=history,
        )

    results = []

    with patch.object(answering, "generate_response", side_effect=tracking_generate_response):
        for q_item in AUDIT_QUESTIONS:
            qid = q_item["id"]
            question = q_item["question"]
            should_find = q_item["should_find"]
            expected_facts = q_item["expected_facts"]

            logger.info("\n" + "=" * 80)
            logger.info("AUDIT QUESTION %d: %s", qid, question)
            contexts_captured.clear()

            # 1. Retrieve candidates directly to inspect query embedding & deduplication
            raw_collection = vector_store._raw_collection()
            embed_model = vector_store.get_embedding_model()
            
            # Check embedding generation
            query_vec = await embed_model.aembed_query(question)
            embedding_generated = len(query_vec) == settings.gemini_embedding_dim

            # Retrieve through enhanced vector_store
            candidates = await vector_store.retrieve_documents(
                question=question,
                k=settings.rag_top_k,
                user_id=user_id,
                include_below_threshold=True,
            )

            retrieved_chunk_ids = [c[0].metadata.get("chunk_id", "unknown") for c in candidates]
            retrieved_sources = list(dict.fromkeys(c[0].metadata.get("source", "unknown") for c in candidates))
            retrieved_scores = [round(c[1], 4) for c in candidates]

            # Detect duplicates from candidate collection
            duplicates_found = sum(1 for c in candidates if c[0].metadata.get("is_duplicate"))

            # 2. Call complete RAG answer pipeline
            answer_res = await answering.answer_with_rag(
                question=question,
                user_id=user_id,
            )
            answer_text = answer_res["answer"]
            llm_context = contexts_captured[-1]["context"] if contexts_captured else "NONE (LLM not invoked)"

            # 3. Verify correctness
            correct = False
            if should_find:
                found_any_fact = any(fact.lower() in answer_text.lower() for fact in expected_facts)
                correct = found_any_fact
            else:
                # Absent questions 11 and 12 must NOT invent answers
                correct = "couldn't find information" in answer_text or answer_text == answering.NO_ANSWER_REPLY

            logger.info("Embedding Generated: %s (%d dims)", "YES" if embedding_generated else "NO", len(query_vec))
            logger.info("Retrieved Chunk IDs: %s", retrieved_chunk_ids)
            logger.info("Retrieved Sources: %s", retrieved_sources)
            logger.info("Scores: %s (Threshold: %.2f)", retrieved_scores, settings.rag_min_score)
            logger.info("Duplicates in unique results: %d", duplicates_found)
            logger.info("Context passed to LLM: %s", f"{len(llm_context)} chars" if llm_context != "NONE (LLM not invoked)" else "NONE")
            logger.info("AI Answer: %s", answer_text[:200])
            logger.info("Result: %s", "PASS" if correct else "FAIL")

            results.append({
                "id": qid,
                "question": question,
                "embedding_generated": "YES" if embedding_generated else "NO",
                "retrieved_chunk_ids": retrieved_chunk_ids,
                "retrieved_sources": retrieved_sources,
                "scores": retrieved_scores,
                "duplicates_found": duplicates_found,
                "context_sent": f"{len(llm_context)} chars" if llm_context != "NONE (LLM not invoked)" else "NONE",
                "context_preview": llm_context[:150] if llm_context != "NONE (LLM not invoked)" else "NONE",
                "answer": answer_text,
                "correct": correct,
            })
            await asyncio.sleep(1.0)

    # Print final summary table
    print("\n" + "=" * 90)
    print("STEP 5 AUDIT VERIFICATION TABLE (12 QUESTIONS)")
    print("=" * 90)
    all_ok = True
    for r in results:
        status_flag = "PASS" if r["correct"] else "FAIL"
        if not r["correct"]:
            all_ok = False
        print(f"[{status_flag}] Q{r['id']}: {r['question']}")
        print(f"       Embedding Gen : {r['embedding_generated']}")
        print(f"       Chunk IDs     : {r['retrieved_chunk_ids']}")
        print(f"       Sources       : {r['retrieved_sources']}")
        print(f"       Scores        : {r['scores']}")
        print(f"       Duplicates    : {r['duplicates_found']}")
        print(f"       Context Sent  : {r['context_sent']}")
        print(f"       Answer        : {r['answer']}")
        print("-" * 90)

    print(f"\nFinal Audit Verdict: {'ALL 12 QUESTIONS PASSED' if all_ok else 'SOME QUESTIONS FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_audit()))

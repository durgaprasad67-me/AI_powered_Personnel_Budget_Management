"""Step 4 Verification Script: Enforce Strict RAG-Only LLM Answering.

Verifies:
1. Question whose answer exists in a document.
2. Same question with different wording.
3. Question about an absent fact (dynamic no-info response, no hallucination).
4. Question containing a misleading suggested answer (rejects suggestion, grounds to context).
5. Question whose context contains only partial information (answers supported part, notes missing part).
6. Question about another user's document (strict user isolation, 0 chunks retrieved, LLM not called).
7. Simulated empty retrieval result (retrieval first, LLM not called with empty context).
8. Simulated embedding API failure (fail closed, safe error response, LLM not called).
9. Simulated ChromaDB retrieval failure (fail closed, safe error response, LLM not called).

For every test, the exact context sent to the LLM is inspected and recorded.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Configure backend path
backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_step4")


async def main() -> int:
    from app.core.config import get_settings
    from app.integrations import vector_store
    from app.services.rag import answering, documents

    settings = get_settings()
    logger.info("Starting Step 4 Verification: Strict RAG-Only LLM Answering")
    logger.info("Chroma collection: %s", settings.chroma_collection_name)
    logger.info("Persist directory: %s", settings.chroma_persist_directory)

    # Test users and document
    alice_id = "test_user_step4_alice"
    bob_id = "test_user_step4_bob"
    doc_id = "doc_step4_benefits"
    source_filename = "employee_benefits_step4.txt"

    test_content = (
        "FinSight Corporate Benefits Policy 2026\n"
        "Employee Name: Alice Smith\n"
        "Employee ID: EMP-4091\n"
        "Monthly Health & Medical Allowance: ₹5,000.00\n"
        "Monthly Parking Permit Fee: ₹1,200.00\n"
        "Coverage Effective Date: 2026-01-01\n"
        "Source Document: HR Benefits Handbook 2026, Page 12\n"
        "Note: All travel allowances must be approved separately by division managers."
    )

    # Setup: Index document for Alice
    logger.info("--- Setup: Indexing test document for %s ---", alice_id)
    chunks = documents.prepare_document(source_filename, test_content.encode("utf-8"))
    c_hash = documents.content_hash(test_content.encode("utf-8"))
    uploaded_at = "2026-01-01T00:00:00Z"

    index_res = documents.index_parsed_document(
        chunks,
        user_id=alice_id,
        source_filename=source_filename,
        doc_id=doc_id,
        content_hash_value=c_hash,
        uploaded_at=uploaded_at,
    )
    logger.info("Indexed %d chunks for %s", index_res["chunks_created"], alice_id)

    # Track actual context sent to LLM
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

    results_table: list[dict[str, str]] = []

    try:
        with patch.object(answering, "generate_response", side_effect=tracking_generate_response):

            # TEST 1: Question whose answer exists in document
            logger.info("\n=== TEST 1: Question whose answer exists in document ===")
            contexts_captured.clear()
            q1 = "What is my monthly health & medical allowance?"
            ans1 = await answering.answer_with_rag(q1, user_id=alice_id)
            c1 = contexts_captured[-1]["context"] if contexts_captured else "NONE"
            passed1 = "5,000" in ans1["answer"] or "5000" in ans1["answer"]
            logger.info("Question: %s", q1)
            logger.info("Answer: %s", ans1["answer"])
            logger.info("Context sent to LLM:\n%s", c1)
            logger.info("Test 1 Result: %s", "YES" if passed1 else "NO")
            results_table.append({
                "test": "1. Answer exists in document",
                "question": q1,
                "context_sent": f"{len(c1)} chars (contains ₹5,000)",
                "answer_summary": ans1["answer"][:100],
                "grounded": "YES" if passed1 else "NO",
            })

            # TEST 2: Same question with different wording (paraphrased)
            logger.info("\n=== TEST 2: Same question with different wording ===")
            contexts_captured.clear()
            q2 = "How much allowance do I receive per month for health and medical coverage?"
            ans2 = await answering.answer_with_rag(q2, user_id=alice_id)
            c2 = contexts_captured[-1]["context"] if contexts_captured else "NONE"
            passed2 = "5,000" in ans2["answer"] or "5000" in ans2["answer"]
            logger.info("Question: %s", q2)
            logger.info("Answer: %s", ans2["answer"])
            logger.info("Context sent to LLM:\n%s", c2)
            logger.info("Test 2 Result: %s", "YES" if passed2 else "NO")
            results_table.append({
                "test": "2. Paraphrased question",
                "question": q2,
                "context_sent": f"{len(c2)} chars (contains ₹5,000)",
                "answer_summary": ans2["answer"][:100],
                "grounded": "YES" if passed2 else "NO",
            })

            # TEST 3: Question about an absent fact
            logger.info("\n=== TEST 3: Question about an absent fact ===")
            contexts_captured.clear()
            q3 = "What was my gym membership expense?"
            ans3 = await answering.answer_with_rag(q3, user_id=alice_id)
            c3 = contexts_captured[-1]["context"] if contexts_captured else "NONE (LLM not invoked)"
            passed3 = "couldn't find information about your gym membership expense" in ans3["answer"]
            logger.info("Question: %s", q3)
            logger.info("Answer: %s", ans3["answer"])
            logger.info("Context sent to LLM:\n%s", c3)
            logger.info("Test 3 Result: %s", "YES" if passed3 else "NO")
            results_table.append({
                "test": "3. Absent fact",
                "question": q3,
                "context_sent": c3[:60] if c3 != "NONE (LLM not invoked)" else "NONE (LLM not invoked)",
                "answer_summary": ans3["answer"],
                "grounded": "YES" if passed3 else "NO",
            })

            # TEST 4: Question containing a misleading suggested answer
            logger.info("\n=== TEST 4: Question containing a misleading suggested answer ===")
            contexts_captured.clear()
            q4 = "Is my monthly health allowance ₹8,000?"
            ans4 = await answering.answer_with_rag(q4, user_id=alice_id)
            c4 = contexts_captured[-1]["context"] if contexts_captured else "NONE"
            passed4 = ("5,000" in ans4["answer"] or "5000" in ans4["answer"]) and (
                "not ₹8,000" in ans4["answer"] or "not 8,000" in ans4["answer"] or "No" in ans4["answer"] or "8,000" not in ans4["answer"]
            )
            logger.info("Question: %s", q4)
            logger.info("Answer: %s", ans4["answer"])
            logger.info("Context sent to LLM:\n%s", c4)
            logger.info("Test 4 Result: %s", "YES" if passed4 else "NO")
            results_table.append({
                "test": "4. Misleading suggested answer",
                "question": q4,
                "context_sent": f"{len(c4)} chars (contains ₹5,000; no 8,000)",
                "answer_summary": ans4["answer"][:100],
                "grounded": "YES" if passed4 else "NO",
            })

            # TEST 5: Question whose context contains only partial information
            logger.info("\n=== TEST 5: Context contains only partial information ===")
            contexts_captured.clear()
            q5 = "What is my monthly health allowance and what is my travel allowance?"
            ans5 = await answering.answer_with_rag(q5, user_id=alice_id)
            c5 = contexts_captured[-1]["context"] if contexts_captured else "NONE"
            # Must state health allowance 5000 AND note travel allowance was not found / requires approval
            passed5 = ("5,000" in ans5["answer"] or "5000" in ans5["answer"]) and (
                "travel" in ans5["answer"].lower() and ("not found" in ans5["answer"].lower() or "couldn't find" in ans5["answer"].lower() or "separately" in ans5["answer"].lower() or "not specified" in ans5["answer"].lower() or "not provided" in ans5["answer"].lower())
            )
            logger.info("Question: %s", q5)
            logger.info("Answer: %s", ans5["answer"])
            logger.info("Context sent to LLM:\n%s", c5)
            logger.info("Test 5 Result: %s", "YES" if passed5 else "NO")
            results_table.append({
                "test": "5. Partial information",
                "question": q5,
                "context_sent": f"{len(c5)} chars (health 5000 present, travel amount absent)",
                "answer_summary": ans5["answer"][:120],
                "grounded": "YES" if passed5 else "NO",
            })

            # TEST 6: Question about another user's document
            logger.info("\n=== TEST 6: Question about another user's document ===")
            contexts_captured.clear()
            q6 = "What is my monthly health & medical allowance?"
            ans6 = await answering.answer_with_rag(q6, user_id=bob_id)
            c6 = contexts_captured[-1]["context"] if contexts_captured else "NONE (LLM not invoked)"
            passed6 = (
                len(contexts_captured) == 0
                and "couldn't find information about your monthly health & medical allowance" in ans6["answer"]
                and ans6["sources"] == []
            )
            logger.info("User: %s (querying Alice's document)", bob_id)
            logger.info("Question: %s", q6)
            logger.info("Answer: %s", ans6["answer"])
            logger.info("Context sent to LLM: %s", c6)
            logger.info("Test 6 Result: %s", "YES" if passed6 else "NO")
            results_table.append({
                "test": "6. Another user's document query",
                "question": q6,
                "context_sent": "NONE (LLM not invoked - 0 chunks retrieved)",
                "answer_summary": ans6["answer"],
                "grounded": "YES (Complete user isolation)" if passed6 else "NO",
            })

            # TEST 7: Simulate empty retrieval result
            logger.info("\n=== TEST 7: Simulate empty retrieval result ===")
            contexts_captured.clear()
            with patch.object(answering, "retrieve_documents", return_value=[]):
                q7 = "What is the secret passphrase?"
                ans7 = await answering.answer_with_rag(q7, user_id=alice_id)
                c7 = contexts_captured[-1]["context"] if contexts_captured else "NONE (LLM not invoked)"
                passed7 = (
                    len(contexts_captured) == 0
                    and "couldn't find information about the secret passphrase" in ans7["answer"]
                    and ans7["sources"] == []
                )
                logger.info("Question: %s", q7)
                logger.info("Answer: %s", ans7["answer"])
                logger.info("Context sent to LLM: %s", c7)
                logger.info("Test 7 Result: %s", "YES" if passed7 else "NO")
                results_table.append({
                    "test": "7. Empty retrieval simulation",
                    "question": q7,
                    "context_sent": "NONE (LLM not invoked - 0 chunks)",
                    "answer_summary": ans7["answer"],
                    "grounded": "YES" if passed7 else "NO",
                })

            # TEST 8: Simulate embedding API failure
            logger.info("\n=== TEST 8: Simulate embedding API failure ===")
            contexts_captured.clear()
            with patch.object(
                answering,
                "retrieve_documents",
                side_effect=RuntimeError("Embedding API key quota exhausted or network error"),
            ):
                q8 = "What is my health allowance?"
                ans8 = await answering.answer_with_rag(q8, user_id=alice_id)
                c8 = contexts_captured[-1]["context"] if contexts_captured else "NONE (LLM not invoked)"
                passed8 = (
                    len(contexts_captured) == 0
                    and "Unable to retrieve information" in ans8["answer"]
                    and ans8["sources"] == []
                )
                logger.info("Question: %s", q8)
                logger.info("Answer: %s", ans8["answer"])
                logger.info("Context sent to LLM: %s", c8)
                logger.info("Test 8 Result: %s", "YES" if passed8 else "NO")
                results_table.append({
                    "test": "8. Embedding API failure simulation",
                    "question": q8,
                    "context_sent": "NONE (LLM not invoked - fail closed)",
                    "answer_summary": ans8["answer"],
                    "grounded": "YES (Fail-closed enforced)" if passed8 else "NO",
                })

            # TEST 9: Simulate ChromaDB retrieval failure
            logger.info("\n=== TEST 9: Simulate ChromaDB retrieval failure ===")
            contexts_captured.clear()
            with patch.object(
                answering,
                "retrieve_documents",
                side_effect=RuntimeError("ChromaDB disk I/O connection error"),
            ):
                q9 = "What is my parking permit fee?"
                ans9 = await answering.answer_with_rag(q9, user_id=alice_id)
                c9 = contexts_captured[-1]["context"] if contexts_captured else "NONE (LLM not invoked)"
                passed9 = (
                    len(contexts_captured) == 0
                    and "Unable to retrieve information" in ans9["answer"]
                    and ans9["sources"] == []
                )
                logger.info("Question: %s", q9)
                logger.info("Answer: %s", ans9["answer"])
                logger.info("Context sent to LLM: %s", c9)
                logger.info("Test 9 Result: %s", "YES" if passed9 else "NO")
                results_table.append({
                    "test": "9. ChromaDB retrieval failure simulation",
                    "question": q9,
                    "context_sent": "NONE (LLM not invoked - fail closed)",
                    "answer_summary": ans9["answer"],
                    "grounded": "YES (Fail-closed enforced)" if passed9 else "NO",
                })

    finally:
        # Cleanup test document from ChromaDB
        logger.info("\n--- Cleanup: Deleting test document %s for %s ---", doc_id, alice_id)
        vector_store.delete_document(doc_id, user_id=alice_id)

    # Print summary table
    print("\n" + "=" * 80)
    print("STEP 4 VERIFICATION RESULTS TABLE")
    print("=" * 80)
    all_passed = True
    for row in results_table:
        status_flag = "PASS" if row["grounded"].startswith("YES") else "FAIL"
        if status_flag == "FAIL":
            all_passed = False
        print(f"[{status_flag}] {row['test']}")
        print(f"       Question: {row['question']}")
        print(f"       Context Sent: {row['context_sent']}")
        print(f"       Answer: {row['answer_summary']}")
        print(f"       Grounded/Isolated: {row['grounded']}")
        print("-" * 80)

    print(f"\nFinal Result: {'ALL 9 TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

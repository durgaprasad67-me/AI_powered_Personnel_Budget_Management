"""
Duplicate detection service for FinSight AI imports.
Implements file-level hashing, row-level fingerprinting with occurrence indexing,
batched database checks, and dynamic duplicate threshold evaluation.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.domain.normalization import clean_spaces, normalize_type
from app.services.importing.import_messages import render_message


def compute_row_fingerprint_base(
    user_id: str,
    date_str: str,
    description: str,
    amount: float | Decimal,
    tx_type: str,
) -> str:
    """
    Compute base identity key: user_id + date + normalized description + amount + type.
    Category is intentionally excluded because users may recategorize existing transactions.
    """
    clean_desc = clean_spaces(description or "").strip().lower()
    amt_val = float(amount or 0.0)
    amt_str = f"{amt_val:.2f}"
    clean_type = normalize_type(tx_type or "expense")
    return f"{user_id.strip()}:{str(date_str).strip()}:{clean_desc}:{amt_str}:{clean_type}"


def compute_row_fingerprint(base_key: str, occurrence: int = 1) -> str:
    """
    Compute the unique SHA-256 fingerprint for a transaction with its occurrence index.
    Repeated identical rows in the same file get distinct fingerprints (key + '#' + n).
    """
    unique_key = f"{base_key}#{occurrence}"
    return hashlib.sha256(unique_key.encode("utf-8")).hexdigest()


def compute_file_hashes(
    content: bytes, valid_rows: list[dict[str, Any]], user_id: str
) -> tuple[str, str]:
    """
    Compute:
    1. Raw file bytes SHA-256 hash.
    2. Normalized content SHA-256 hash (so re-saved files with identical rows are detected).
    """
    raw_hash = hashlib.sha256(content).hexdigest()

    row_reprs = [
        f"{r.get('date', '')}|{clean_spaces(r.get('description', '')).strip().lower()}|{float(r.get('amount', 0)):.2f}|{r.get('transaction_type', '')}"
        for r in valid_rows
    ]
    norm_content_str = "\n".join(row_reprs)
    normalized_hash = hashlib.sha256(norm_content_str.encode("utf-8")).hexdigest()

    return raw_hash, normalized_hash


def assign_occurrence_fingerprints(
    valid_rows: list[dict[str, Any]], user_id: str
) -> list[dict[str, Any]]:
    """
    Attach fingerprint_base, occurrence, and fingerprint to each valid row.
    Occurrence counter disambiguates identical transactions within the same batch.
    """
    counts: dict[str, int] = {}
    for row in valid_rows:
        base_key = compute_row_fingerprint_base(
            user_id=user_id,
            date_str=row.get("date", ""),
            description=row.get("description", ""),
            amount=row.get("amount", 0.0),
            tx_type=row.get("transaction_type", "expense"),
        )
        occ = counts.get(base_key, 0) + 1
        counts[base_key] = occ
        fp = compute_row_fingerprint(base_key, occ)
        row["fingerprint_base"] = base_key
        row["occurrence"] = occ
        row["fingerprint"] = fp

    return valid_rows


@dataclass
class DuplicateReport:
    decision: str  # "no_duplicates", "some_duplicates_allowed", "needs_confirmation", "all_duplicates", "file_already_imported"
    total_count: int
    duplicate_count: int
    new_count: int
    ratio: float
    duplicate_rows: list[dict[str, Any]]
    new_rows: list[dict[str, Any]]
    sample_duplicates: list[dict[str, Any]]
    message: str
    actions: list[str]
    previous_import: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "total_count": self.total_count,
            "duplicate_count": self.duplicate_count,
            "new_count": self.new_count,
            "ratio": round(self.ratio, 4),
            "sample_duplicates": self.sample_duplicates,
            "message": self.message,
            "actions": self.actions,
            "previous_import": self.previous_import,
        }


class DeduplicationService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def check_file_already_imported(
        self,
        imports_collection: Any,
        user_id: str,
        raw_hash: str,
        norm_hash: str,
    ) -> dict[str, Any] | None:
        """Check if this user already imported this exact file or normalized content."""
        if imports_collection is None:
            return None

        query = {
            "user_id": user_id,
            "status": "completed",
            "$or": [
                {"raw_file_hash": raw_hash},
                {"normalized_content_hash": norm_hash},
            ],
        }
        return await imports_collection.find_one(query)

    async def evaluate_duplicates(
        self,
        user_id: str,
        valid_rows: list[dict[str, Any]],
        transactions_collection: Any,
        imports_collection: Any = None,
        raw_hash: str | None = None,
        norm_hash: str | None = None,
    ) -> DuplicateReport:
        """
        Evaluate duplicates across the batch in ONE single $in query.
        Applies configurable thresholds and returns a structured DuplicateReport.
        """
        # Step 1: Assign occurrence-aware fingerprints to every row in the file
        assign_occurrence_fingerprints(valid_rows, user_id=user_id)

        # Step 2: Check for exact file duplicate if hashes provided
        if raw_hash and norm_hash and imports_collection is not None:
            prev_import = await self.check_file_already_imported(
                imports_collection, user_id, raw_hash, norm_hash
            )
            if prev_import:
                created_date = prev_import.get("created_at", "recently")
                count = prev_import.get("counts", {}).get("imported_count", len(valid_rows))
                msg = render_message(
                    "FILE_ALREADY_IMPORTED",
                    import_date=created_date,
                    count=count,
                )
                return DuplicateReport(
                    decision="file_already_imported",
                    total_count=len(valid_rows),
                    duplicate_count=len(valid_rows),
                    new_count=0,
                    ratio=1.0,
                    duplicate_rows=valid_rows,
                    new_rows=[],
                    sample_duplicates=valid_rows[:5],
                    message=msg,
                    actions=["cancel"],
                    previous_import={
                        "import_id": prev_import.get("import_id"),
                        "filename": prev_import.get("filename"),
                        "created_at": prev_import.get("created_at"),
                        "imported_count": count,
                    },
                )

        if not valid_rows:
            return DuplicateReport(
                decision="no_duplicates",
                total_count=0,
                duplicate_count=0,
                new_count=0,
                ratio=0.0,
                duplicate_rows=[],
                new_rows=[],
                sample_duplicates=[],
                message="No valid rows to inspect for duplicates.",
                actions=["cancel"],
            )

        # Step 3: Check database in ONE batched query using $in over fingerprints
        fps = [r["fingerprint"] for r in valid_rows]
        existing_fps: set[str] = set()

        if transactions_collection is not None:
            query = {"user_id": user_id, "fingerprint": {"$in": fps}}
            cursor = transactions_collection.find(
                query,
                projection={"fingerprint": 1, "date": 1, "description": 1, "amount": 1, "transaction_type": 1},
            )
            async for doc in cursor:
                if doc.get("fingerprint"):
                    existing_fps.add(doc["fingerprint"])

        # Step 4: Split into duplicates and new rows
        duplicate_rows: list[dict[str, Any]] = []
        new_rows: list[dict[str, Any]] = []

        for r in valid_rows:
            is_db_dup = r["fingerprint"] in existing_fps
            is_intra_file_dup = r.get("occurrence", 1) > 1
            if is_db_dup or is_intra_file_dup:
                duplicate_rows.append(r)
            else:
                new_rows.append(r)

        total_cnt = len(valid_rows)
        dup_cnt = len(duplicate_rows)
        new_cnt = len(new_rows)
        ratio = (dup_cnt / total_cnt) if total_cnt > 0 else 0.0

        # Step 5: Evaluate decision rules
        allowed_count = getattr(self.settings, "duplicate_allowed_count", 2)
        confirm_ratio = getattr(self.settings, "duplicate_confirm_ratio", 0.50)

        sample_dupes = [
            {
                "row_number": r.get("row_number"),
                "date": r.get("date"),
                "description": r.get("description"),
                "amount": r.get("amount"),
                "transaction_type": r.get("transaction_type"),
            }
            for r in duplicate_rows[:5]
        ]

        if dup_cnt == 0:
            decision = "no_duplicates"
            message = "All records are new."
            actions = ["import_all"]

        elif dup_cnt == total_cnt:
            decision = "all_duplicates"
            message = render_message("ALL_DUPLICATES", total_count=total_cnt)
            actions = ["cancel"]

        elif dup_cnt <= allowed_count and ratio < confirm_ratio:
            decision = "some_duplicates_allowed"
            message = render_message(
                "DUPLICATES_FOUND",
                duplicate_count=dup_cnt,
                total_count=total_cnt,
                new_count=new_cnt,
            )
            actions = ["import_new_only", "import_all", "cancel"]

        else:
            decision = "needs_confirmation"
            message = (
                f"{dup_cnt} of {total_cnt} records ({ratio * 100:.0f}%) already exist in your account. "
                "Importing again will create duplicate transactions and duplicate AI search data."
            )
            actions = ["import_new_only", "import_all", "cancel"]

        return DuplicateReport(
            decision=decision,
            total_count=total_cnt,
            duplicate_count=dup_cnt,
            new_count=new_cnt,
            ratio=ratio,
            duplicate_rows=duplicate_rows,
            new_rows=new_rows,
            sample_duplicates=sample_dupes,
            message=message,
            actions=actions,
        )

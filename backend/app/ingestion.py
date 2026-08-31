from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .catalog import stable_movie_id
from .normalization import normalize_text

BIOGRAPHY_MARKERS = ("was born", "is an actor", "is an actress", "filmography", "personal life")


@dataclass(slots=True)
class ValidationOutcome:
    accepted: list[dict[str, Any]]
    quarantined: list[dict[str, Any]]
    warnings: list[dict[str, Any]]


def identity_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    """Transparent entity matching; external ID or title/year/director/cast evidence."""
    left_external = left.get("external_id") or left.get("source_identifier")
    right_external = right.get("external_id") or right.get("source_identifier")
    if left_external and right_external and str(left_external) == str(right_external):
        return 1.0
    left_title = normalize_text(str(left.get("canonical_title") or left.get("title") or ""))
    right_title = normalize_text(str(right.get("canonical_title") or right.get("title") or ""))
    if not left_title or left_title != right_title:
        return 0.0
    score = 0.55
    left_year, right_year = left.get("release_year"), right.get("release_year")
    if left_year and right_year:
        score += 0.2 if str(left_year) == str(right_year) else -0.25
    left_director = normalize_text(str(left.get("director") or ""))
    right_director = normalize_text(str(right.get("director") or ""))
    if left_director and right_director and left_director == right_director:
        score += 0.15
    left_cast = set(normalize_text(str(left.get("cast") or "")).split())
    right_cast = set(normalize_text(str(right.get("cast") or "")).split())
    if left_cast and right_cast:
        score += 0.1 * (len(left_cast & right_cast) / len(left_cast | right_cast))
    return max(0.0, min(1.0, score))


class IngestionService:
    def __init__(self, trusted_poster_hosts: tuple[str, ...], version_dir: Path):
        self.trusted_poster_hosts = set(trusted_poster_hosts)
        self.version_dir = version_dir

    def validate(
        self, records: Iterable[dict[str, Any]], transformation_version: str
    ) -> ValidationOutcome:
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        identities: set[tuple[str, str, str]] = set()
        current_year = datetime.now(UTC).year
        for index, envelope in enumerate(records):
            raw = dict(envelope.get("movie") or {})
            source_system = str(envelope.get("source_system") or "").strip()
            source_identifier = str(envelope.get("source_identifier") or "").strip()
            reasons: list[str] = []
            title = str(raw.get("canonical_title") or raw.get("title") or "").strip()
            overview = str(raw.get("overview") or "").strip()
            language = str(raw.get("language") or "Tamil").strip()
            director = str(raw.get("director") or "").strip()
            if not title:
                reasons.append("missing_title")
            year = raw.get("release_year")
            if year is not None:
                try:
                    year = int(year)
                    if not 1900 <= year <= current_year + 3:
                        reasons.append("release_year_out_of_range")
                except (TypeError, ValueError):
                    reasons.append("invalid_release_year")
            runtime = raw.get("runtime_minutes")
            if runtime is not None:
                try:
                    if not 20 <= int(runtime) <= 600:
                        reasons.append("runtime_out_of_range")
                except (TypeError, ValueError):
                    reasons.append("invalid_runtime")
            if len(overview) < 40:
                reasons.append("overview_too_short")
            if any(marker in overview.casefold() for marker in BIOGRAPHY_MARKERS):
                reasons.append("overview_appears_biographical")
            poster = str(raw.get("poster_url") or "").strip()
            if poster:
                parsed = urlparse(poster)
                if parsed.scheme != "https":
                    reasons.append("poster_must_use_https")
                elif self.trusted_poster_hosts and parsed.hostname not in self.trusted_poster_hosts:
                    warnings.append(
                        {"index": index, "code": "untrusted_poster_host", "host": parsed.hostname}
                    )
            identity = (normalize_text(title), str(year or ""), normalize_text(language))
            if identity in identities:
                reasons.append("duplicate_title_year_language")
            identities.add(identity)
            confidence = float(envelope.get("confidence", 1.0))
            if confidence < 0.65:
                reasons.append("identity_confidence_below_threshold")
            provenance = {
                "source_system": source_system,
                "source_identifier": source_identifier,
                "retrieved_at": str(envelope.get("retrieved_at") or datetime.now(UTC).isoformat()),
                "transformation_version": transformation_version,
                "confidence": confidence,
            }
            raw.update(
                {
                    "id": raw.get("id") or stable_movie_id(title, director, year, language),
                    "canonical_title": title,
                    "release_year": year,
                    "language": language,
                    "provenance": provenance,
                    "data_quality_status": "validated" if not reasons else "quarantined",
                }
            )
            if reasons:
                quarantined.append({"index": index, "record": raw, "reasons": reasons})
            else:
                accepted.append(raw)
        return ValidationOutcome(accepted, quarantined, warnings)

    def run(
        self,
        records: Iterable[dict[str, Any]],
        transformation_version: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        outcome = self.validate(records, transformation_version)
        # Retrieval timestamps are provenance, not movie identity/content. A
        # repeated import of the same payload must retain one stable version.
        digest_records: list[dict[str, Any]] = []
        for record in outcome.accepted:
            digest_record = dict(record)
            provenance = dict(digest_record.get("provenance") or {})
            provenance.pop("retrieved_at", None)
            digest_record["provenance"] = provenance
            digest_records.append(digest_record)
        encoded = json.dumps(digest_records, sort_keys=True, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        version = f"ingestion-{digest[:12]}"
        output_path: str | None = None
        if not dry_run and outcome.accepted:
            self.version_dir.mkdir(parents=True, exist_ok=True)
            destination = self.version_dir / f"movies-{digest}.json"
            if not destination.exists():
                descriptor, temporary = tempfile.mkstemp(
                    prefix="ingestion-", suffix=".json", dir=self.version_dir
                )
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                        json.dump(outcome.accepted, handle, ensure_ascii=False, indent=2)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, destination)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            output_path = str(destination)
        return {
            "dataset_version": version,
            "content_hash": digest,
            "dry_run": dry_run,
            "accepted_count": len(outcome.accepted),
            "quarantined_count": len(outcome.quarantined),
            "quarantined": outcome.quarantined,
            "warnings": outcome.warnings,
            "output_path": output_path,
            "idempotent": bool(output_path and Path(output_path).exists()),
            "requires_promotion": not dry_run and bool(outcome.accepted),
        }

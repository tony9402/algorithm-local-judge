"""Persistent, cache-independent history for Judge submissions."""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from commons.job_persistence import AtomicJsonFile
from judge.core import security_limits
from judge.core.errors import JudgeError
from judge.core.paths import cache_root, ensure_inside, user_data_root, validate_safe_id
from judge.utils.limited_io import copy_limited
from judge.web.service_common import normalize_language_id
from judge.web.source_history_metadata import source_entry_metadata, source_file_for_entry
from judge.web.source_history_paths import source_history_root, source_id_from_path

SUBMISSION_LIFECYCLES = {"queued", "running", "completed", "cancelled", "interrupted"}
SUBMISSION_VERDICTS = {
    "accepted",
    "wrong_answer",
    "compile_error",
    "runtime_error",
    "time_limit",
    "memory_limit",
    "system_error",
}
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
SAFE_SOURCE_BASENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+$-]{0,127}$")


class ActiveSubmissionError(JudgeError):
    """Raised when deletion would discard an in-flight submission."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_timestamp(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value or 0), UTC).isoformat()
    except (OSError, OverflowError, TypeError, ValueError):
        return datetime.fromtimestamp(0, UTC).isoformat()


def _chmod_private(path: Path, mode: int) -> None:
    if os.name != "nt":
        path.chmod(mode)


def _source_suffix(source: Path) -> str:
    suffix = source.suffix.lower()
    if suffix and len(suffix) <= 12 and suffix[1:].isalnum():
        return suffix
    return ".txt"


def _snapshot_filename(source: Path) -> str:
    basename = source.name
    if basename not in {
        "",
        ".",
        "..",
        "metadata.json",
        "result.json",
    } and SAFE_SOURCE_BASENAME_RE.fullmatch(basename):
        return basename
    return f"source{_source_suffix(source)}"


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    cases = result.get("cases") if isinstance(result.get("cases"), list) else []
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    return {
        "caseCount": len(cases),
        "firstFailedCase": result.get("firstFailedCase"),
        "metrics": metrics,
        "message": result.get("message"),
        "statusLabel": result.get("statusLabel"),
    }


def _without_host_paths(value: Any) -> Any:
    """Copy result data while omitting machine-specific absolute paths."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key) in {"runDir", "sourcePath"}:
                continue
            if isinstance(item, str) and Path(item).is_absolute():
                continue
            cleaned[str(key)] = _without_host_paths(item)
        return cleaned
    if isinstance(value, list):
        return [_without_host_paths(item) for item in value]
    return value


def _durable_result(result: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "runId",
        "problemId",
        "profile",
        "language",
        "status",
        "cases",
        "metrics",
        "warmup",
        "message",
        "firstFailedCase",
        "passed",
        "statusLabel",
        "errorKind",
        "failureStage",
        "failureStageLabel",
        "failureDetails",
        "sourceId",
        "submissionId",
    }
    return _without_host_paths({key: value for key, value in result.items() if key in allowed})


class SubmissionStore:
    """Store immutable source snapshots and durable submission summaries."""

    def __init__(
        self,
        root: Path | str | None = None,
        legacy_history_root: Path | str | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve() if root else user_data_root() / "submissions"
        self.legacy_history_root = (
            Path(legacy_history_root).expanduser().resolve()
            if legacy_history_root is not None
            else source_history_root()
        )
        self._lock = threading.RLock()
        self._prepare_root()
        self.reconcile_interrupted()

    def _prepare_root(self) -> None:
        # Importing the ASGI module must remain possible in read-only diagnostic
        # environments. The first write still reports a normal persistence error.
        with contextlib.suppress(OSError):
            self.root.mkdir(parents=True, exist_ok=True)
            _chmod_private(self.root, 0o700)

    def _entry_dir(self, submission_id: str) -> Path:
        validate_safe_id("submission id", submission_id)
        return ensure_inside(self.root / submission_id, self.root)

    def _metadata_file(self, submission_id: str) -> AtomicJsonFile:
        return AtomicJsonFile(self._entry_dir(submission_id) / "metadata.json")

    def _read_metadata(self, submission_id: str) -> dict[str, Any]:
        payload = self._metadata_file(submission_id).read()
        if not isinstance(payload, dict):
            raise JudgeError(f"submission not found: {submission_id}")
        return payload

    def _write_metadata(self, metadata: dict[str, Any]) -> None:
        submission_id = str(metadata.get("submissionId") or "")
        if not self._metadata_file(submission_id).write(metadata):
            raise JudgeError(f"unable to persist submission: {submission_id}")

    def _tombstones(self) -> set[str]:
        payload = AtomicJsonFile(self.root / "tombstones.json").read()
        if not isinstance(payload, dict) or not isinstance(payload.get("legacySourceIds"), list):
            return set()
        return {str(item) for item in payload["legacySourceIds"] if item}

    def _write_tombstones(self, source_ids: set[str]) -> None:
        if not AtomicJsonFile(self.root / "tombstones.json").write(
            {"schemaVersion": 1, "legacySourceIds": sorted(source_ids)}
        ):
            raise JudgeError("unable to persist submission deletion marker")

    def create(
        self,
        source: Path,
        *,
        problem_id: str,
        profile: str | None,
        language: str | None,
        source_mode: str,
    ) -> dict[str, Any]:
        validate_safe_id("problem id", problem_id)
        submission_id = uuid.uuid4().hex
        entry_dir = self._entry_dir(submission_id)
        entry_dir.mkdir(parents=True)
        _chmod_private(entry_dir, 0o700)
        snapshot = entry_dir / _snapshot_filename(source)
        temporary_snapshot = entry_dir / f".{snapshot.name}.{uuid.uuid4().hex}.tmp"
        try:
            with source.open("rb") as input_file:
                copy_limited(
                    input_file,
                    temporary_snapshot,
                    limit_bytes=security_limits.MAX_SOURCE_UPLOAD_BYTES,
                    label="submission source",
                )
            with temporary_snapshot.open("rb") as copied:
                os.fsync(copied.fileno())
            os.replace(temporary_snapshot, snapshot)
            _chmod_private(snapshot, 0o600)
            created_at = _now()
            metadata = {
                "schemaVersion": 1,
                "submissionId": submission_id,
                "problemId": problem_id,
                "profile": (profile or "").strip() or "full",
                "language": normalize_language_id(language) or language,
                "filename": source.name,
                "sourceMode": source_mode,
                "sourceFile": snapshot.name,
                "sourceSize": snapshot.stat().st_size,
                "legacySourceId": source_id_from_path(source),
                "lifecycle": "queued",
                "verdict": None,
                "jobId": None,
                "runId": None,
                "resultSummary": None,
                "error": None,
                "createdAt": created_at,
                "startedAt": None,
                "finishedAt": None,
                "updatedAt": created_at,
            }
            self._write_metadata(metadata)
            return dict(metadata)
        except Exception:
            temporary_snapshot.unlink(missing_ok=True)
            shutil.rmtree(entry_dir, ignore_errors=True)
            raise

    def update(
        self,
        submission_id: str,
        *,
        lifecycle: str | None = None,
        verdict: str | None = None,
        job_id: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if lifecycle is not None and lifecycle not in SUBMISSION_LIFECYCLES:
            raise JudgeError(f"invalid submission lifecycle: {lifecycle}")
        if verdict is not None and verdict not in SUBMISSION_VERDICTS:
            verdict = "system_error"
        with self._lock:
            metadata = self._read_metadata(submission_id)
            now = _now()
            if lifecycle is not None:
                current_lifecycle = str(metadata.get("lifecycle") or "")
                terminal = {"completed", "cancelled", "interrupted"}
                if current_lifecycle in terminal:
                    return dict(metadata)
                allowed = {
                    "queued": {"queued", "running", "completed", "cancelled", "interrupted"},
                    "running": {"running", "completed", "cancelled", "interrupted"},
                }
                if current_lifecycle not in terminal and lifecycle not in allowed.get(
                    current_lifecycle, set()
                ):
                    raise JudgeError(
                        f"invalid submission lifecycle transition: {current_lifecycle} -> {lifecycle}"
                    )
                metadata["lifecycle"] = lifecycle
                if lifecycle == "running" and not metadata.get("startedAt"):
                    metadata["startedAt"] = now
                if lifecycle in {"completed", "cancelled", "interrupted"}:
                    metadata["finishedAt"] = metadata.get("finishedAt") or now
            if job_id is not None:
                metadata["jobId"] = job_id
            if result is not None:
                result_copy = _durable_result(result)
                result_file = AtomicJsonFile(self._entry_dir(submission_id) / "result.json")
                if not result_file.write(result_copy):
                    raise JudgeError(f"unable to persist submission result: {submission_id}")
                run_id = result_copy.get("runId")
                metadata["runId"] = str(run_id) if run_id else None
                metadata["resultSummary"] = _result_summary(result_copy)
                verdict = str(result_copy.get("status") or verdict or "system_error")
                if verdict not in SUBMISSION_VERDICTS:
                    verdict = "system_error"
            if verdict is not None:
                metadata["verdict"] = verdict
            if error is not None:
                metadata["error"] = error
            metadata["updatedAt"] = now
            self._write_metadata(metadata)
            return dict(metadata)

    def mark_running(self, submission_id: str) -> dict[str, Any]:
        return self.update(submission_id, lifecycle="running")

    def complete(self, submission_id: str, result: dict[str, Any]) -> dict[str, Any]:
        return self.update(submission_id, lifecycle="completed", result=result)

    def fail(
        self,
        submission_id: str,
        error: Exception | str,
        *,
        verdict: str = "system_error",
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = str(error)
        durable_result = dict(result or {})
        durable_result["status"] = verdict
        durable_result["message"] = message
        return self.update(
            submission_id,
            lifecycle="completed",
            verdict=verdict,
            error=message,
            result=durable_result,
        )

    def cancel(self, submission_id: str) -> dict[str, Any]:
        return self.update(submission_id, lifecycle="cancelled")

    def bind_job(self, submission_id: str, job_id: str) -> dict[str, Any]:
        validate_safe_id("job id", job_id)
        return self.update(submission_id, job_id=job_id)

    def reconcile_interrupted(self) -> int:
        changed = 0
        if not self.root.exists():
            return changed
        with self._lock:
            for entry_dir in self.root.iterdir():
                if not entry_dir.is_dir():
                    continue
                with contextlib.suppress(JudgeError):
                    metadata = self._read_metadata(entry_dir.name)
                    if metadata.get("lifecycle") not in {"queued", "running"}:
                        continue
                    self.update(
                        entry_dir.name,
                        lifecycle="interrupted",
                        error="애플리케이션이 재시작되어 제출이 중단되었습니다.",
                    )
                    changed += 1
        return changed

    def _stored_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if not self.root.exists():
            return entries
        for entry_dir in self.root.iterdir():
            if not entry_dir.is_dir():
                continue
            with contextlib.suppress(JudgeError):
                entries.append(self._read_metadata(entry_dir.name))
        return entries

    def _legacy_entries(self, claimed_source_ids: set[str]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        root = self.legacy_history_root
        if not root.exists():
            return entries
        for entry_dir in root.iterdir():
            if not entry_dir.is_dir() or entry_dir.name in claimed_source_ids:
                continue
            try:
                metadata = source_entry_metadata(entry_dir)
            except (OSError, TypeError, ValueError):
                continue
            if not metadata or not isinstance(metadata.get("lastRun"), dict):
                continue
            last_run = metadata["lastRun"]
            status = str(last_run.get("status") or "system_error")
            entries.append(
                {
                    "schemaVersion": 0,
                    "submissionId": f"legacy-{entry_dir.name}",
                    "legacy": True,
                    "legacySourceId": entry_dir.name,
                    "problemId": last_run.get("problemId") or metadata.get("problemId"),
                    "profile": last_run.get("profile") or "full",
                    "language": metadata.get("languageId") or metadata.get("language"),
                    "filename": metadata.get("filename"),
                    "sourceMode": metadata.get("sourceMode"),
                    "sourceSize": metadata.get("size"),
                    "lifecycle": "completed",
                    "verdict": status if status in SUBMISSION_VERDICTS else "system_error",
                    "jobId": None,
                    "runId": last_run.get("runId"),
                    "resultSummary": {
                        "caseCount": last_run.get("caseCount", 0),
                        "firstFailedCase": last_run.get("firstFailedCase"),
                        "metrics": last_run.get("metrics") or {},
                    },
                    "error": None,
                    "createdAt": _safe_timestamp(
                        last_run.get("savedAt") or metadata.get("savedAt")
                    ),
                    "startedAt": None,
                    "finishedAt": None,
                    "updatedAt": _safe_timestamp(
                        last_run.get("savedAt") or metadata.get("savedAt")
                    ),
                }
            )
        return entries

    def list(
        self,
        *,
        problem_id: str | None = None,
        status: str | None = None,
        language: str | None = None,
        profile: str | None = None,
        query: str | None = None,
        order: str = "newest",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = min(MAX_PAGE_SIZE, max(1, page_size))
        with self._lock:
            entries = self._stored_entries()
            claimed = self._tombstones() | {
                str(entry.get("legacySourceId"))
                for entry in entries
                if entry.get("legacySourceId")
            }
            entries.extend(self._legacy_entries(claimed))
        if problem_id:
            entries = [entry for entry in entries if entry.get("problemId") == problem_id]
        if status:
            entries = [
                entry
                for entry in entries
                if status in {entry.get("lifecycle"), entry.get("verdict")}
            ]
        if language:
            normalized_language = language.casefold()
            entries = [
                entry
                for entry in entries
                if str(entry.get("language") or "").casefold() == normalized_language
            ]
        if profile:
            entries = [entry for entry in entries if entry.get("profile") == profile]
        if query:
            needle = query.casefold()
            entries = [
                entry
                for entry in entries
                if needle
                in " ".join(
                    str(entry.get(key) or "")
                    for key in (
                        "submissionId",
                        "problemId",
                        "filename",
                        "language",
                        "verdict",
                        "runId",
                        "jobId",
                    )
                ).casefold()
            ]
        reverse = order != "oldest"
        entries.sort(
            key=lambda entry: (str(entry.get("createdAt") or ""), entry["submissionId"]),
            reverse=reverse,
        )
        total = len(entries)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        return {
            "submissions": entries[start : start + page_size],
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": total_pages,
        }

    def detail(self, submission_id: str) -> dict[str, Any]:
        if submission_id.startswith("legacy-"):
            return self._legacy_detail(submission_id.removeprefix("legacy-"))
        metadata = self._read_metadata(submission_id)
        entry_dir = self._entry_dir(submission_id)
        source_file = ensure_inside(entry_dir / str(metadata.get("sourceFile") or ""), entry_dir)
        if not source_file.is_file():
            raise JudgeError(f"submission source not found: {submission_id}")
        result_file = AtomicJsonFile(entry_dir / "result.json")
        result = result_file.read()
        run_id = metadata.get("runId")
        artifact_available = bool(
            run_id and (cache_root() / "runs" / str(run_id) / "result.json").is_file()
        )
        return {
            **metadata,
            "sourceText": source_file.read_text(encoding="utf-8", errors="replace"),
            "result": result if isinstance(result, dict) else None,
            "artifactAvailable": artifact_available,
        }

    def source_path(self, submission_id: str) -> Path:
        metadata = self._read_metadata(submission_id)
        entry_dir = self._entry_dir(submission_id)
        source_file = ensure_inside(entry_dir / str(metadata.get("sourceFile") or ""), entry_dir)
        if source_file.is_symlink() or not source_file.is_file():
            raise JudgeError(f"submission source not found: {submission_id}")
        return source_file

    def _legacy_detail(self, source_id: str) -> dict[str, Any]:
        validate_safe_id("source id", source_id)
        entry_dir = ensure_inside(self.legacy_history_root / source_id, self.legacy_history_root)
        metadata = source_entry_metadata(entry_dir) if entry_dir.is_dir() else None
        source_file = source_file_for_entry(entry_dir, metadata) if metadata else None
        if (
            metadata is None
            or source_file is None
            or not isinstance(metadata.get("lastRun"), dict)
        ):
            raise JudgeError(f"submission not found: legacy-{source_id}")
        source_file = ensure_inside(source_file, self.legacy_history_root)
        if source_file.is_symlink() or not source_file.is_file():
            raise JudgeError(f"submission source not found: legacy-{source_id}")
        matches = self._legacy_entries(set())
        summary = next(
            (entry for entry in matches if entry["submissionId"] == f"legacy-{source_id}"), None
        )
        if summary is None:
            raise JudgeError(f"submission not found: legacy-{source_id}")
        run_id = summary.get("runId")
        result = None
        if run_id:
            result_path = cache_root() / "runs" / str(run_id) / "result.json"
            if result_path.is_file():
                result = AtomicJsonFile(result_path).read()
        return {
            **summary,
            "sourceText": source_file.read_text(encoding="utf-8", errors="replace"),
            "result": result if isinstance(result, dict) else None,
            "artifactAvailable": result is not None,
        }

    def delete(self, submission_id: str) -> dict[str, Any]:
        if submission_id.startswith("legacy-"):
            raise JudgeError("legacy source history cannot be deleted as a submission")
        with self._lock:
            entry_dir = self._entry_dir(submission_id)
            if not entry_dir.is_dir():
                raise JudgeError(f"submission not found: {submission_id}")
            metadata = self._read_metadata(submission_id)
            if metadata.get("lifecycle") in {"queued", "running"}:
                raise ActiveSubmissionError("active submission cannot be deleted")
            source_id = metadata.get("legacySourceId")
            if source_id:
                tombstones = self._tombstones()
                tombstones.add(str(source_id))
                self._write_tombstones(tombstones)
            shutil.rmtree(entry_dir)
        return {"deleted": True, "submissionId": submission_id}

    def clear(self) -> dict[str, Any]:
        """Delete durable submissions while preserving legacy source files."""
        with self._lock:
            stored = self._stored_entries()
            if any(entry.get("lifecycle") in {"queued", "running"} for entry in stored):
                raise ActiveSubmissionError("active submissions cannot be cleared")
            tombstones = self._tombstones()
            tombstones.update(
                str(entry["legacySourceId"]) for entry in stored if entry.get("legacySourceId")
            )
            tombstones.update(
                str(entry["legacySourceId"])
                for entry in self._legacy_entries(set())
                if entry.get("legacySourceId")
            )
            self._write_tombstones(tombstones)
            cleared = 0
            for entry in stored:
                entry_dir = self._entry_dir(str(entry["submissionId"]))
                if entry_dir.is_dir():
                    shutil.rmtree(entry_dir)
                    cleared += 1
        return {"deleted": True, "cleared": cleared}


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "SUBMISSION_LIFECYCLES",
    "SUBMISSION_VERDICTS",
    "ActiveSubmissionError",
    "SubmissionStore",
]

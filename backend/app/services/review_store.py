from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Callable
from uuid import uuid4

from app.services.path_guard import ALLOWED_EXT
from app.services.workspace_context import get_workspace_root


@dataclass
class SnapshotFile:
    path: str
    content: str
    ts: int
    version: int


@dataclass
class SnapshotBatch:
    snapshot_id: str
    workspace_root: str
    files: dict[str, SnapshotFile] = field(default_factory=dict)
    full_workspace: bool = True
    ts: int = field(default_factory=lambda: int(time() * 1000))


@dataclass
class ReviewFileChange:
    path: str
    added: int
    deleted: int
    first_changed_line: int
    before: str
    after: str


@dataclass
class ReviewBatch:
    review_id: str
    snapshot_id: str
    workspace_root: str
    status: str
    files: list[ReviewFileChange]
    ts: int = field(default_factory=lambda: int(time() * 1000))


class ReviewStore:
    def __init__(self) -> None:
        self._snapshots: dict[str, SnapshotBatch] = {}
        self._reviews: dict[str, ReviewBatch] = {}
        self._pending_review_ids: list[str] = []
        self._subscribers: list[Callable[[dict], None]] = []

    def subscribe(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def _unsub() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return _unsub

    def _publish(self, event: dict) -> None:
        for sub in list(self._subscribers):
            sub(event)

    def _now(self) -> int:
        return int(time() * 1000)

    def _iter_workspace_files(self, workspace_root: Path) -> list[Path]:
        files: list[Path] = []
        for file in workspace_root.rglob("*"):
            if not file.is_file():
                continue
            if file.suffix.lower() not in ALLOWED_EXT:
                continue
            files.append(file)
        return files

    def create_snapshot(self, file_paths: list[str] | None = None) -> SnapshotBatch:
        workspace_root = get_workspace_root().resolve()
        raw_files = (
            [self._safe_in_workspace(workspace_root, p) for p in file_paths]
            if file_paths
            else self._iter_workspace_files(workspace_root)
        )
        files: dict[str, SnapshotFile] = {}
        ts = self._now()
        for file in raw_files:
            rel = self._relative_path(workspace_root, file)
            content = file.read_text(encoding="utf-8", errors="ignore")
            files[rel] = SnapshotFile(path=rel, content=content, ts=ts, version=1)

        snapshot = SnapshotBatch(
            snapshot_id=f"snap-{uuid4().hex[:12]}",
            workspace_root=str(workspace_root),
            files=files,
            full_workspace=not bool(file_paths),
            ts=ts,
        )
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot

    def commit_snapshot(self, snapshot_id: str) -> ReviewBatch:
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        workspace_root = Path(snapshot.workspace_root).resolve()

        current_files: dict[str, str] = {}
        if snapshot.full_workspace:
            for file in self._iter_workspace_files(workspace_root):
                rel = self._relative_path(workspace_root, file)
                current_files[rel] = file.read_text(encoding="utf-8", errors="ignore")
            all_paths = sorted(set(snapshot.files.keys()) | set(current_files.keys()))
        else:
            all_paths = sorted(set(snapshot.files.keys()))
            for path in all_paths:
                target = (workspace_root / path).resolve()
                if target.exists() and target.is_file():
                    current_files[path] = target.read_text(encoding="utf-8", errors="ignore")
        changed: list[ReviewFileChange] = []
        for path in all_paths:
            before = snapshot.files.get(path).content if path in snapshot.files else ""
            after = current_files.get(path, "")
            if before == after:
                continue
            added, deleted, first_line = self._compute_change_stat(before, after)
            changed.append(
                ReviewFileChange(
                    path=path,
                    added=added,
                    deleted=deleted,
                    first_changed_line=first_line,
                    before=before,
                    after=after,
                )
            )

        review = ReviewBatch(
            review_id=f"rev-{uuid4().hex[:12]}",
            snapshot_id=snapshot_id,
            workspace_root=snapshot.workspace_root,
            status="pending",
            files=changed,
        )
        self._reviews[review.review_id] = review
        if changed:
            self._pending_review_ids.append(review.review_id)
            self._publish(
                {
                    "type": "review.updated",
                    "review": self.serialize_review(review),
                }
            )
        return review

    def list_pending(self) -> list[dict]:
        out: list[dict] = []
        for review_id in list(self._pending_review_ids):
            review = self._reviews.get(review_id)
            if not review or review.status != "pending":
                continue
            out.append(self.serialize_review(review))
        return out

    def decide(self, review_ids: list[str], action: str) -> dict:
        if action not in {"confirm", "rollback"}:
            raise ValueError("action must be confirm or rollback")
        processed: list[str] = []
        for review_id in review_ids:
            review = self._reviews.get(review_id)
            if not review or review.status != "pending":
                continue
            if action == "rollback":
                self._restore_snapshot(review.snapshot_id, review.files)
                review.status = "rolled_back"
            else:
                review.status = "confirmed"
            processed.append(review_id)
            if review_id in self._pending_review_ids:
                self._pending_review_ids.remove(review_id)
            if review.snapshot_id in self._snapshots:
                del self._snapshots[review.snapshot_id]

        self._publish(
            {
                "type": "review.decision",
                "action": action,
                "review_ids": processed,
                "ts": self._now(),
            }
        )
        return {"action": action, "review_ids": processed}

    def serialize_review(self, review: ReviewBatch) -> dict:
        return {
            "review_id": review.review_id,
            "snapshot_id": review.snapshot_id,
            "workspace_root": review.workspace_root,
            "status": review.status,
            "ts": review.ts,
            "files": [
                {
                    "path": f.path,
                    "added": f.added,
                    "deleted": f.deleted,
                    "first_changed_line": f.first_changed_line,
                    "before": f.before,
                    "after": f.after,
                }
                for f in review.files
            ],
        }

    def _safe_in_workspace(self, workspace_root: Path, path: str) -> Path:
        candidate = Path(path)
        candidate = candidate if candidate.is_absolute() else workspace_root / candidate
        candidate = candidate.resolve()
        if workspace_root not in candidate.parents and candidate != workspace_root:
            raise ValueError(f"path out of workspace: {path}")
        if not candidate.exists() or not candidate.is_file():
            raise ValueError(f"file not found: {path}")
        if candidate.suffix.lower() not in ALLOWED_EXT:
            raise ValueError(f"extension not allowed: {path}")
        return candidate

    def _relative_path(self, workspace_root: Path, file: Path) -> str:
        return file.resolve().relative_to(workspace_root).as_posix()

    def _compute_change_stat(self, before: str, after: str) -> tuple[int, int, int]:
        added = 0
        deleted = 0
        first_line = 1
        current_after_line = 0
        first_found = False
        for line in difflib.ndiff(before.splitlines(), after.splitlines()):
            tag = line[:2]
            if tag == "  ":
                current_after_line += 1
                continue
            if tag == "+ ":
                added += 1
                current_after_line += 1
            elif tag == "- ":
                deleted += 1
            if not first_found:
                first_line = max(current_after_line, 1)
                first_found = True
        return added, deleted, first_line

    def _restore_snapshot(self, snapshot_id: str, files: list[ReviewFileChange]) -> None:
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return
        workspace_root = Path(snapshot.workspace_root).resolve()
        snapshot_paths = set(snapshot.files.keys())
        changed_paths = {item.path for item in files}

        # Remove files created after snapshot.
        for path in changed_paths:
            if path in snapshot_paths:
                continue
            target = (workspace_root / path).resolve()
            if target.exists() and target.is_file():
                target.unlink()

        # Restore snapshot files.
        for path in changed_paths:
            snap = snapshot.files.get(path)
            if not snap:
                continue
            target = (workspace_root / path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(snap.content, encoding="utf-8")


review_store = ReviewStore()

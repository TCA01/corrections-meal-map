from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import uuid
from datetime import datetime
from pathlib import Path

from production.io import atomic_json


def now():
    return datetime.now().astimezone().isoformat()


def load(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def process_alive(pid):
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.OpenProcess.restype = ctypes.c_void_p
        ctypes.windll.kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        ctypes.windll.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            # Access denied means potentially live, not demonstrably dead.
            return ctypes.windll.kernel32.GetLastError() != 87
        code = ctypes.c_ulong()
        try:
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class RunLocked(RuntimeError):
    pass


class RunLock:
    """O_EXCL ownership. Never steal a live, remote, or malformed lock."""
    def __init__(self, path: Path, stale_seconds=21600):
        self.path = path
        self.stale_seconds = stale_seconds
        self.token = uuid.uuid4().hex

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    old = load(self.path)
                    dead_stale = (old["host"] == socket.gethostname()
                                  and time.time() - float(old["created"]) > self.stale_seconds
                                  and not process_alive(int(old["pid"])))
                except (ValueError, KeyError, TypeError):
                    dead_stale = False
                if not dead_stale or attempt:
                    raise RunLocked("update lock held; live/remote/uncertain locks require operator inspection")
                # Recovery guard prevents two reclaimers from renaming each other's new lock.
                guard = self.path.with_name("update.recovery.lock")
                try:
                    guard_fd = os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    raise RunLocked("lock recovery already running; inspect if interrupted")
                os.close(guard_fd)
                try:
                    if load(self.path) != old:
                        raise RunLocked("lock owner changed during recovery")
                    os.replace(self.path, self.path.with_name(f"update.stale-{self.token}.json"))
                finally:
                    guard.unlink()
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"token": self.token, "pid": os.getpid(), "host": socket.gethostname(),
                           "created": time.time()}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            return self

    def __exit__(self, *args):
        if load(self.path, {}).get("token") == self.token:
            self.path.unlink()


REASONS = {"NEW_LAYOUT", "UNSUPPORTED_FORMAT", "UNRESOLVED_INSTITUTION", "AMBIGUOUS_DOCUMENT_ROLE",
           "MISSING_DATE", "MISSING_MEAL", "UNRESOLVED_FORMULA", "EXCEL_ERROR", "MENU_ARTIFACT",
           "DATA_CONFLICT", "DOWNLOAD_FAILED", "SOURCE_CHANGED", "VALIDATION_FAILED",
           "SOURCE_CHANGED_REVIEW_REQUIRED"}


class ReviewQueue:
    def __init__(self, path):
        self.path = path
        self.items = load(path, [])
        self.new_count = 0

    def add(self, item, reason, summary):
        if reason not in REASONS:
            raise ValueError("unknown review reason")
        identity = f"{item['post_id']}:{item['attachment_id']}:{reason}"
        key = hashlib.sha256(identity.encode()).hexdigest()[:24]
        old = next((v for v in self.items if v["review_id"] == key), None)
        if old is None:
            old = {"review_id": key, "first_seen": now(), "status": "OPEN"}
            self.items.append(old)
            self.new_count += 1
        old.update(last_seen=now(), institution=item.get("institution_id"), post_id=item["post_id"],
                   attachment_id=item["attachment_id"], filename=item["filename"], reason_code=reason,
                   severity="warning", source_url=item.get("post_url"), parser_format=item.get("detected_format"),
                   layout_family=item.get("layout_family"), issue_summary=summary)
        # IGNORED persists; resolved issues reopen if actually observed again.
        if old["status"] == "RESOLVED":
            old["status"] = "OPEN"

    def resolve_source(self, item):
        for value in self.items:
            if (value["post_id"], value["attachment_id"]) == (item["post_id"], item["attachment_id"]) and value["status"] == "OPEN":
                value.update(status="RESOLVED", last_seen=now())

    def save(self):
        atomic_json(self.path, self.items)

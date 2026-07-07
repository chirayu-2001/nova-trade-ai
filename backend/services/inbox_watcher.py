"""Simulated SU inbox — Part 2's "trigger".

Watches `settings.inbox_dir` for new folders that represent an incoming
email from a shipping unit (SU): an `email.json` metadata file plus one or
more PDF attachments. The moment a folder looks complete, it auto-triggers
the same Part 1 pipeline (Extractor -> Validator -> Cross-Validate -> Router)
that the manual upload flow uses — no new extraction/validation/routing
logic is needed here, only the trigger.

Folder convention:

    data/inbox/<slug>/
        email.json   # {"from", "subject", "customer_id", "body"?, "received_at"?}
        *.pdf        # one or more trade document attachments

Processed folders are archived under `data/inbox/_processed/` (or
`_error/` on failure) so they are never reprocessed.
"""

import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from backend.config.settings import settings
from backend.pipeline.graph import run_pipeline

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 1.5
PROCESSED_DIRNAME = "_processed"
ERROR_DIRNAME = "_error"

# How long to wait after starting the native OS observer before checking
# whether its emitter thread actually attached. Native backends (FSEvents on
# macOS, in particular) can fail to attach depending on process sandboxing —
# when that happens the emitter thread logs an error and exits almost
# immediately, so a short grace period is enough to detect it reliably.
NATIVE_OBSERVER_STARTUP_GRACE_SECONDS = 0.5

# In-memory registry of every inbox item seen this process lifetime, keyed by
# folder slug (== inbox item id). Good enough for a single-process demo app;
# the durable record of a *processed* email lives in the shipments table.
_inbox_items: dict[str, dict] = {}
_items_lock = threading.Lock()
_debounce_timers: dict[str, threading.Timer] = {}
_observer: Optional[Observer] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_item(item_id: str, **fields) -> None:
    with _items_lock:
        _inbox_items.setdefault(item_id, {"id": item_id})
        _inbox_items[item_id].update(fields)


def get_inbox_items() -> list[dict]:
    """Return all known inbox items, most recently received first."""
    with _items_lock:
        items = [dict(v) for v in _inbox_items.values()]
    items.sort(key=lambda i: i.get("received_at") or "", reverse=True)
    return items


def _list_pdfs(folder: str) -> list[str]:
    return sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(".pdf")
    )


def _archive_folder(folder: str, subdir: str) -> None:
    """Move a processed/errored folder out of the watch root so it can never
    re-trigger the pipeline."""
    try:
        watch_root = os.path.dirname(folder)
        dest_root = os.path.join(watch_root, subdir)
        os.makedirs(dest_root, exist_ok=True)
        dest = os.path.join(dest_root, os.path.basename(folder))
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.move(folder, dest)
    except Exception as e:
        logger.error(f"Failed to archive inbox folder {folder}: {e}")


def _process_email_folder(folder: str) -> None:
    """Validate an inbox folder, then run the Part 1 pipeline on it."""
    item_id = os.path.basename(folder)

    if not os.path.isdir(folder):
        return  # A previous debounce firing already handled/moved it

    email_meta_path = os.path.join(folder, "email.json")
    if not os.path.exists(email_meta_path):
        logger.warning(f"Inbox folder {folder} has no email.json yet — waiting")
        return

    pdfs = _list_pdfs(folder)
    if not pdfs:
        logger.warning(f"Inbox folder {folder} has no PDF attachments yet — waiting")
        return

    try:
        with open(email_meta_path) as f:
            meta = json.load(f)
    except Exception as e:
        _set_item(item_id, status="error", error=f"Could not read email.json: {e}")
        return

    customer_id = meta.get("customer_id")
    if not customer_id:
        _set_item(item_id, status="error", error="email.json is missing customer_id")
        return

    sender = meta.get("from", "unknown@supplier.com")
    subject = meta.get("subject", "Shipment Documents")
    received_at = meta.get("received_at") or _now()
    shipment_id = f"SHP-{uuid.uuid4().hex[:8].upper()}"

    _set_item(
        item_id,
        status="processing",
        sender=sender,
        subject=subject,
        body=meta.get("body", ""),
        customer_id=customer_id,
        attachments=[os.path.basename(p) for p in pdfs],
        received_at=received_at,
        shipment_id=shipment_id,
        error=None,
    )

    def _run():
        try:
            run_pipeline(
                document_paths=pdfs,
                customer_id=customer_id,
                shipment_id=shipment_id,
                source="email",
                sender_email=sender,
                subject=subject,
                received_at=received_at,
            )
            _set_item(item_id, status="processed")
            _archive_folder(folder, PROCESSED_DIRNAME)
        except Exception as e:
            logger.error(f"Inbox pipeline run failed for {folder}: {e}")
            _set_item(item_id, status="error", error=str(e))
            _archive_folder(folder, ERROR_DIRNAME)

    threading.Thread(target=_run, daemon=True, name=f"inbox-pipeline-{item_id}").start()


def _schedule_processing(folder: str) -> None:
    """Debounce so a burst of file-copy events for one folder only fires the
    pipeline once, after the folder looks stable."""
    item_id = os.path.basename(folder)
    with _items_lock:
        existing = _inbox_items.get(item_id)
        if existing and existing.get("status") in ("processing", "processed"):
            return
        _inbox_items.setdefault(
            item_id, {"id": item_id, "status": "new", "received_at": _now()}
        )
        timer = _debounce_timers.get(item_id)
        if timer:
            timer.cancel()
        timer = threading.Timer(DEBOUNCE_SECONDS, _process_email_folder, args=(folder,))
        timer.daemon = True
        _debounce_timers[item_id] = timer
        timer.start()


class _InboxEventHandler(FileSystemEventHandler):
    """Maps raw filesystem events under the watch root back to the top-level
    email folder they belong to, and ignores our own archive subfolders."""

    def __init__(self, watch_root: str):
        self.watch_root = os.path.abspath(watch_root)

    def _folder_for(self, path: str) -> Optional[str]:
        path = os.path.abspath(path)
        if path == self.watch_root or not path.startswith(self.watch_root):
            return None
        rel = os.path.relpath(path, self.watch_root)
        top = rel.split(os.sep)[0]
        if top.startswith("_") or top.startswith("."):
            return None
        return os.path.join(self.watch_root, top)

    def on_created(self, event):
        folder = self._folder_for(event.src_path)
        if folder:
            _schedule_processing(folder)

    def on_modified(self, event):
        folder = self._folder_for(event.src_path)
        if folder:
            _schedule_processing(folder)


def _scan_existing(watch_root: str) -> None:
    """Pick up any email folders already sitting in the inbox at startup —
    covers the "drop files while the server was off" case."""
    for name in os.listdir(watch_root):
        if name.startswith("_") or name.startswith("."):
            continue
        folder = os.path.join(watch_root, name)
        if os.path.isdir(folder):
            _schedule_processing(folder)


def _start_observer_with_fallback(handler: FileSystemEventHandler, watch_root: str):
    """Start the native OS filesystem observer, falling back to watchdog's
    polling observer if the native backend fails to attach.

    On macOS, FSEvents can fail with `SystemError: Cannot start fsevents
    stream` depending on how the process was launched/sandboxed — the
    emitter thread catches that exception, logs it, and simply exits, so
    `on_created`/`on_modified` never fire again for the lifetime of the
    process. That failure is silent from the Observer's point of view (no
    exception propagates to this function), so we detect it by checking
    whether the emitter thread is still alive shortly after starting.
    """
    observer = Observer()
    observer.schedule(handler, watch_root, recursive=True)
    observer.daemon = True
    observer.start()

    time.sleep(NATIVE_OBSERVER_STARTUP_GRACE_SECONDS)
    emitters = list(observer.emitters)
    native_ok = bool(emitters) and all(e.is_alive() for e in emitters)

    if native_ok:
        return observer, "native"

    logger.warning(
        "Native filesystem observer failed to attach (commonly "
        "'Cannot start fsevents stream' on macOS under certain sandboxes/launch "
        "contexts) — falling back to a polling observer so new inbox folders "
        "are still detected."
    )
    try:
        observer.stop()
        observer.join(timeout=2)
    except Exception:
        pass

    polling_observer = PollingObserver(timeout=1.0)
    polling_observer.schedule(handler, watch_root, recursive=True)
    polling_observer.daemon = True
    polling_observer.start()
    return polling_observer, "polling"


def start_inbox_watcher() -> None:
    """Start watching settings.inbox_dir in a background thread. Idempotent —
    safe to call once from the FastAPI startup event."""
    global _observer
    if _observer is not None:
        return

    watch_root = os.path.abspath(settings.inbox_dir)
    os.makedirs(watch_root, exist_ok=True)

    _scan_existing(watch_root)

    handler = _InboxEventHandler(watch_root)
    observer, backend = _start_observer_with_fallback(handler, watch_root)
    _observer = observer
    logger.info(f"Inbox watcher started on {watch_root} ({backend} observer)")


def stop_inbox_watcher() -> None:
    global _observer
    if _observer is not None:
        _observer.stop()
        _observer.join(timeout=2)
        _observer = None


def simulate_incoming_email(seed_name: Optional[str] = None) -> dict:
    """Copy one canned email from data/inbox_seed/ into the watched inbox
    folder. Lets a demo trigger a "new email just arrived" moment on click,
    instead of depending on real filesystem timing."""
    seed_root = os.path.abspath(settings.inbox_seed_dir)
    if not os.path.isdir(seed_root):
        raise FileNotFoundError(f"No seed emails found at {seed_root}")

    available = sorted(
        d for d in os.listdir(seed_root)
        if os.path.isdir(os.path.join(seed_root, d))
    )
    if not available:
        raise FileNotFoundError(f"No seed email folders inside {seed_root}")

    chosen = seed_name if seed_name in available else available[int(time.time()) % len(available)]

    src = os.path.join(seed_root, chosen)
    watch_root = os.path.abspath(settings.inbox_dir)
    os.makedirs(watch_root, exist_ok=True)
    dest_id = f"{chosen}_{uuid.uuid4().hex[:6]}"
    dest = os.path.join(watch_root, dest_id)
    shutil.copytree(src, dest)
    return {"id": dest_id, "seed": chosen}

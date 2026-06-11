from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import importlib
import json
from pathlib import Path
import sys
import threading
from typing import Any
from zoneinfo import ZoneInfo

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
SCHEDULE_TIME = time(hour=1, minute=0, second=0)
DEFAULT_MIN_UPVOTES = 5
DEFAULT_POLL_SECONDS = 300
STATE_FILE_NAME = "service_state.json"


@dataclass(slots=True)
class SourceScheduler:
    data_dir: Path
    thread: threading.Thread
    stop_event: threading.Event

    def stop(self) -> None:
        self.stop_event.set()


def start_source_scheduler(
    data_dir: Path,
    *,
    base_dir: Path,
    min_upvotes: int = DEFAULT_MIN_UPVOTES,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
) -> SourceScheduler:
    """Start the Hugging Face Daily scheduler in a daemon thread.

    Runs every day at 01:00:00 America/Los_Angeles time and fetches the
    previous Pacific calendar day's Hugging Face Daily Papers.
    """

    resolved_data_dir = data_dir.resolve()
    resolved_data_dir.mkdir(parents=True, exist_ok=True)
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_run_scheduler_loop,
        name="paper-reader-source-pdt-0100",
        kwargs={
            "data_dir": resolved_data_dir,
            "base_dir": base_dir.resolve(),
            "min_upvotes": min_upvotes,
            "poll_seconds": poll_seconds,
            "stop_event": stop_event,
        },
        daemon=True,
    )
    thread.start()
    return SourceScheduler(data_dir=resolved_data_dir, thread=thread, stop_event=stop_event)


def _run_scheduler_loop(
    *,
    data_dir: Path,
    base_dir: Path,
    min_upvotes: int,
    poll_seconds: int,
    stop_event: threading.Event,
) -> None:
    _ensure_source_package_on_path(base_dir)
    _log(
        "service_start",
        data_dir=str(data_dir),
        min_upvotes=min_upvotes,
        schedule_time_pacific=SCHEDULE_TIME.strftime("%H:%M:%S"),
        timezone=str(PACIFIC_TZ),
        behavior="fetch previous Pacific calendar day",
    )

    last_announced_next_run: str | None = None
    while not stop_event.is_set():
        now_pacific = datetime.now(PACIFIC_TZ)
        run_key = now_pacific.date().isoformat()
        scheduled_for_today = datetime.combine(now_pacific.date(), SCHEDULE_TIME, tzinfo=PACIFIC_TZ)
        state = _load_state(data_dir)
        already_ran_today = state.get("last_successful_run_date_pacific") == run_key

        if now_pacific >= scheduled_for_today and not already_ran_today:
            try:
                _collect_previous_pacific_day(data_dir, min_upvotes=min_upvotes, run_reason="scheduled_previous_pacific_day")
                last_announced_next_run = None
            except Exception as exc:  # pragma: no cover - operational safety path
                _log("run_failed", error=str(exc))
            _sleep(stop_event, max(30, poll_seconds))
            continue

        next_run = _next_run_after(now_pacific)
        if already_ran_today:
            next_run = datetime.combine(now_pacific.date() + timedelta(days=1), SCHEDULE_TIME, tzinfo=PACIFIC_TZ)
        next_key = next_run.isoformat()
        if next_key != last_announced_next_run:
            _log(
                "waiting",
                now_pacific=now_pacific.isoformat(),
                next_run_pacific=next_run.isoformat(),
                seconds_until_next_run=max(0, int((next_run - now_pacific).total_seconds())),
                last_successful_run_date_pacific=state.get("last_successful_run_date_pacific"),
                last_target_date_pacific=state.get("last_target_date_pacific"),
            )
            last_announced_next_run = next_key
        _sleep(stop_event, min(max(5, poll_seconds), max(5, int((next_run - now_pacific).total_seconds()))))


def _collect_previous_pacific_day(data_dir: Path, *, min_upvotes: int, run_reason: str) -> Path:
    target_date = datetime.now(PACIFIC_TZ).date() - timedelta(days=1)
    return _collect_date(data_dir, target_date, min_upvotes=min_upvotes, run_reason=run_reason)


def _collect_date(data_dir: Path, target_date: date, *, min_upvotes: int, run_reason: str) -> Path:
    huggingface_module = importlib.import_module("paper_reader_source.huggingface")
    service_module = importlib.import_module("paper_reader_source.service")

    now_pacific = datetime.now(PACIFIC_TZ)
    now_utc = datetime.now(timezone.utc)
    snapshot = huggingface_module.fetch_daily_snapshot(target_date.isoformat())
    filtered = huggingface_module.filter_papers_by_upvotes(snapshot, min_upvotes=min_upvotes, inclusive=True)

    day_dir = service_module.day_directory(data_dir, target_date)
    pdf_dir = day_dir / service_module.PDF_SUBDIR_NAME
    pdf_dir.mkdir(parents=True, exist_ok=True)

    manifest_papers: list[dict[str, Any]] = []
    downloaded_count = 0
    existing_count = 0
    failed_count = 0
    for paper in filtered:
        download_result = service_module.ensure_pdf_downloaded(pdf_dir, paper)
        if download_result.downloaded:
            if download_result.error == "already_exists":
                existing_count += 1
            else:
                downloaded_count += 1
        else:
            failed_count += 1

        paper_payload = paper.to_dict()
        paper_payload.update(
            {
                "pdf_url": download_result.pdf_url,
                "pdf_rel_path": download_result.pdf_rel_path,
                "pdf_file_name": download_result.pdf_file_name,
                "pdf_downloaded": download_result.downloaded,
            }
        )
        if download_result.error and download_result.error != "already_exists":
            paper_payload["pdf_error"] = download_result.error
        manifest_papers.append(paper_payload)

    manifest_path = day_dir / service_module.MANIFEST_FILE_NAME
    service_module.write_json_atomic(
        manifest_path,
        {
            "run_reason": run_reason,
            "run_date_pacific": now_pacific.date().isoformat(),
            "target_date_pacific": target_date.isoformat(),
            "saved_at_pacific": now_pacific.isoformat(),
            "saved_at_utc": now_utc.isoformat(),
            "schedule_timezone": str(PACIFIC_TZ),
            "schedule_time_pacific": SCHEDULE_TIME.strftime("%H:%M:%S"),
            "source": "huggingface_daily_papers",
            "source_url": snapshot.source_url,
            "snapshot_date": snapshot.date_string,
            "filter": {"field": "upvotes", "operator": ">=", "value": min_upvotes},
            "paper_count": len(manifest_papers),
            "download_summary": {
                "downloaded": downloaded_count,
                "existing": existing_count,
                "failed": failed_count,
            },
            "papers": manifest_papers,
        },
    )
    service_module.write_json_atomic(
        data_dir / STATE_FILE_NAME,
        {
            "last_successful_run_date_pacific": now_pacific.date().isoformat(),
            "last_target_date_pacific": target_date.isoformat(),
            "last_saved_file": str(manifest_path),
            "last_snapshot_date": snapshot.date_string,
            "updated_at_utc": now_utc.isoformat(),
        },
    )
    _log(
        "run_complete",
        run_reason=run_reason,
        target_date_pacific=target_date.isoformat(),
        snapshot_date=snapshot.date_string,
        saved_file=str(manifest_path),
        paper_count=len(manifest_papers),
        pdf_downloaded=downloaded_count,
        pdf_existing=existing_count,
        pdf_failed=failed_count,
    )
    return manifest_path


def _ensure_source_package_on_path(base_dir: Path) -> None:
    source_project = base_dir / "paper-reader-source"
    if source_project.exists():
        source_path = str(source_project.resolve())
        if source_path not in sys.path:
            sys.path.insert(0, source_path)


def _load_state(data_dir: Path) -> dict[str, Any]:
    state_path = data_dir / STATE_FILE_NAME
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _next_run_after(now_pacific: datetime) -> datetime:
    today_target = datetime.combine(now_pacific.date(), SCHEDULE_TIME, tzinfo=PACIFIC_TZ)
    if now_pacific < today_target:
        return today_target
    return datetime.combine(now_pacific.date() + timedelta(days=1), SCHEDULE_TIME, tzinfo=PACIFIC_TZ)


def _sleep(stop_event: threading.Event, seconds: int) -> None:
    stop_event.wait(max(1, seconds))


def _log(event: str, **fields: Any) -> None:
    now = datetime.now(timezone.utc).isoformat()
    if fields:
        details = " ".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in fields.items())
        print(f"[{now}] source_scheduler.{event} {details}", flush=True)
        return
    print(f"[{now}] source_scheduler.{event}", flush=True)

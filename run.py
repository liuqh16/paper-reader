from __future__ import annotations

import os
from pathlib import Path

from src.paper_reader.app import create_app, load_env_file_values

BASE_DIR = Path(__file__).resolve().parent
ENV_VALUES = load_env_file_values(BASE_DIR / ".env")


def env_setting(key: str, default: str = "") -> str:
    return ENV_VALUES.get(key) or os.environ.get(key) or default


def env_path(key: str) -> Path | None:
    value = env_setting(key).strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def env_flag(key: str, default: bool = False) -> bool:
    value = env_setting(key).strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no", "off"}


codex_home = env_setting("CODEX_HOME", "/root/.codex").strip()
if codex_home and os.environ.get("CODEX_HOME") in {None, "~/.codex", ""}:
    os.environ["CODEX_HOME"] = str(Path(codex_home).expanduser())

app = create_app(
    env_path("PAPER_READER_LIBRARY_ROOT"),
    env_path("PAPER_READER_SOURCE_ARCHIVE_ROOT"),
    start_source_scheduler=env_flag("PAPER_READER_ENABLE_SOURCE_SCHEDULER", True),
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)

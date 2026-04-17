from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .models import Paper, PromptResult

INDEX_FILES = (".paper_reader_index.json", ".paper_reader_done_index.json")
SUMMARY_DIR_NAME = ".paper-reader-ai"


class CorpusLoader:
    def __init__(self, library_root: Path):
        self.library_root = library_root.resolve()
        self.summary_root = self.library_root / SUMMARY_DIR_NAME

    def load(self) -> list[Paper]:
        papers: dict[str, Paper] = {}
        for file_name in INDEX_FILES:
            path = self.library_root / file_name
            if not path.exists():
                continue
            payload = self._load_json(path)
            for item in payload.get("records", []):
                if not isinstance(item, dict):
                    continue
                rel_path = str(item.get("rel_path") or "").strip()
                if not rel_path:
                    continue
                paper = papers.get(rel_path)
                if paper is None:
                    paper = Paper(
                        rel_path=rel_path,
                        title=str(item.get("display_title") or item.get("title") or Path(rel_path).stem),
                        sort_date=item.get("sort_date"),
                        extracted_date=item.get("extracted_date"),
                        is_done=bool(item.get("is_done", False)),
                    )
                    papers[rel_path] = paper
                for slug in item.get("prompt_result_slugs", []) or []:
                    prompt = self._load_prompt_result(rel_path, str(slug))
                    if prompt is not None:
                        paper.prompt_results[prompt.slug] = prompt

        return sorted(papers.values(), key=lambda paper: (paper.sort_date or "0000-00-00", paper.title.lower()), reverse=True)

    def _load_prompt_result(self, rel_path: str, slug: str) -> PromptResult | None:
        prompt_path = self.summary_root / Path(rel_path) / f"{slug}.md"
        if not prompt_path.exists() and slug == "core-zh":
            legacy_path = self.summary_root / Path(rel_path).parent / f"{Path(rel_path).stem}.explained.zh.md"
            prompt_path = legacy_path
        if not prompt_path.exists():
            return None

        text = prompt_path.read_text(encoding="utf-8")
        header, body = parse_prompt_markdown(text)
        return PromptResult(
            slug=slug,
            generated_at=header.get("Generated at") or header.get("generated_at"),
            header=header,
            body=body,
            path=prompt_path,
        )

    def _load_json(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


def parse_prompt_markdown(text: str) -> tuple[dict[str, str], str]:
    if "\n---\n" in text:
        header_text, body = text.split("\n---\n", 1)
    else:
        header_text, body = "", text

    header: dict[str, str] = {}
    for line in header_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        header[key.strip()] = value.strip().strip("`")
    return header, body.strip()

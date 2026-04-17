from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


@dataclass(slots=True)
class PromptResult:
    slug: str
    generated_at: str | None
    header: dict[str, str]
    body: str
    path: Path


@dataclass(slots=True)
class Paper:
    rel_path: str
    title: str
    sort_date: str | None
    extracted_date: str | None
    is_done: bool
    prompt_results: dict[str, PromptResult] = field(default_factory=dict)
    combined_text: str = ""
    sentences: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    gap_tags: list[str] = field(default_factory=list)
    novelty_score: int = 0
    turning_score: int = 0
    evidence_sentences: list[str] = field(default_factory=list)
    limitation_sentences: list[str] = field(default_factory=list)
    claim_sentences: list[str] = field(default_factory=list)

    @property
    def paper_date(self) -> date | None:
        if not self.sort_date:
            return None
        try:
            return datetime.fromisoformat(self.sort_date).date()
        except ValueError:
            return None

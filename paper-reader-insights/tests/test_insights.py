from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paper_reader_insights.analysis import InsightAnalyzer
from paper_reader_insights.loader import CorpusLoader


class InsightPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / ".paper-reader-ai").mkdir(parents=True, exist_ok=True)

        records = [
            self._record("2201.00001.pdf", "Agent Memory Benchmark", "2022-01-01", False, ["core-zh"]),
            self._record("2403.00002.pdf", "Dynamic Agent Arena", "2024-03-01", False, ["core-zh"]),
            self._record("2604.00003.pdf", "Skill Transfer for Long-Horizon Agents", "2026-04-01", False, ["core-zh"]),
            self._record("2604.00004.pdf", "Real-world Web Agent Evaluation", "2026-04-05", False, ["core-zh"]),
        ]
        payload = {"records": records}
        (self.root / ".paper_reader_index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.root / ".paper_reader_done_index.json").write_text(json.dumps({"records": []}, ensure_ascii=False, indent=2), encoding="utf-8")

        self._write_prompt(
            "2201.00001.pdf",
            "core-zh",
            "这篇论文提出一个 benchmark 来分析 agent memory。它说明长期任务里记忆仍然是挑战。",
        )
        self._write_prompt(
            "2403.00002.pdf",
            "core-zh",
            "这篇论文提出一个动态 arena，强调 belief revision 和 real-world evaluation。方法上开始加入 verification。",
        )
        self._write_prompt(
            "2604.00003.pdf",
            "core-zh",
            "这篇论文提出 self-evolving skill library，用于 long-horizon agent。它显示 skill transfer 能明显提升，但真实 benchmark 仍然稀缺。",
        )
        self._write_prompt(
            "2604.00004.pdf",
            "core-zh",
            "这篇论文聚焦 real-world web agent benchmark。作者指出 production evaluation 仍然不足，用户偏好和 personalization 还是挑战。",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _record(self, rel_path: str, title: str, sort_date: str, is_done: bool, slugs: list[str]) -> dict[str, object]:
        return {
            "rel_path": rel_path,
            "title": title,
            "display_title": title,
            "sort_date": sort_date,
            "extracted_date": sort_date,
            "is_done": is_done,
            "prompt_result_slugs": slugs,
        }

    def _write_prompt(self, rel_path: str, slug: str, body: str) -> None:
        path = self.root / ".paper-reader-ai" / rel_path / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# Core\n\n- Source file: `{rel_path}`\n- Prompt slug: `{slug}`\n- Generated at: `2026-04-12T00:00:00`\n\n---\n\n{body}\n",
            encoding="utf-8",
        )

    def test_pipeline_generates_all_three_insight_layers(self) -> None:
        papers = CorpusLoader(self.root).load()
        bundle = InsightAnalyzer(papers).build()

        self.assertIn("Dynamic Survey", bundle.history_markdown)
        self.assertIn("Momentum Dashboard", bundle.momentum_markdown)
        self.assertIn("Opportunity Map", bundle.opportunities_markdown)
        self.assertIn("agent", json.dumps(bundle.json_payload, ensure_ascii=False).lower())


if __name__ == "__main__":
    unittest.main()

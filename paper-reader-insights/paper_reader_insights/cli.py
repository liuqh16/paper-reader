from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import InsightAnalyzer
from .loader import CorpusLoader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate AutoResearch insight artifacts from the paper-reader corpus.")
    parser.add_argument(
        "--library-root",
        default="docs/papers",
        help="Paper library root that contains .paper_reader_index.json and .paper-reader-ai/",
    )
    parser.add_argument(
        "--output-dir",
        default="paper-reader-insights/output",
        help="Directory where markdown/json insight artifacts are written.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    library_root = Path(args.library_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    papers = CorpusLoader(library_root).load()
    bundle = InsightAnalyzer(papers).build()

    (output_dir / "insights-overview.md").write_text(bundle.overview_markdown, encoding="utf-8")
    (output_dir / "dynamic-survey.md").write_text(bundle.history_markdown, encoding="utf-8")
    (output_dir / "momentum-dashboard.md").write_text(bundle.momentum_markdown, encoding="utf-8")
    (output_dir / "opportunity-map.md").write_text(bundle.opportunities_markdown, encoding="utf-8")
    (output_dir / "insights.json").write_text(json.dumps(bundle.json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Generated insight artifacts in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

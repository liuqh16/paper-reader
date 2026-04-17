from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import math
import re

from .models import Paper
from .taxonomy import (
    ASSET_DEFINITIONS,
    CLAIM_CUES,
    GAP_DEFINITIONS,
    LIMITATION_CUES,
    METHOD_DEFINITIONS,
    NOVELTY_CUES,
    THEME_DEFINITIONS,
    TURNING_CUES,
    labels_for,
    match_tags,
)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?\.])\s+|\n+")
MAX_EVIDENCE_PER_SECTION = 6
HOT_WINDOW_DAYS = (30, 60, 90)
MAX_THEME_PREVALENCE = 0.5
MAX_MOMENTUM_THEME_PREVALENCE = 0.65
METHOD_TO_GAP_HINTS = {
    "memory": {"long_horizon", "personalization", "grounding"},
    "retrieval": {"grounding", "transfer"},
    "verification": {"grounding", "evaluation_realism"},
    "skill_library": {"long_horizon", "dynamic_reliability", "transfer"},
    "planning": {"long_horizon", "dynamic_reliability"},
    "benchmark_design": {"evaluation_realism"},
    "synthetic_data": {"cost_efficiency", "evaluation_realism"},
    "self_evolution": {"dynamic_reliability", "transfer"},
}


@dataclass(slots=True)
class InsightBundle:
    overview_markdown: str
    history_markdown: str
    momentum_markdown: str
    opportunities_markdown: str
    json_payload: dict[str, object]


class InsightAnalyzer:
    def __init__(self, papers: list[Paper]):
        self.papers = papers
        self.theme_labels = labels_for([definition.slug for definition in THEME_DEFINITIONS], THEME_DEFINITIONS)
        self.method_labels = labels_for([definition.slug for definition in METHOD_DEFINITIONS], METHOD_DEFINITIONS)
        self.asset_labels = labels_for([definition.slug for definition in ASSET_DEFINITIONS], ASSET_DEFINITIONS)
        self.gap_labels = labels_for([definition.slug for definition in GAP_DEFINITIONS], GAP_DEFINITIONS)

    def build(self) -> InsightBundle:
        enriched = [self._enrich_paper(paper) for paper in self.papers if paper.prompt_results]
        history = self._build_history(enriched)
        momentum = self._build_momentum(enriched)
        opportunities = self._build_opportunities(enriched, momentum)
        overview = self._build_overview(history, momentum, opportunities, len(enriched))
        payload = {
            "paper_count": len(enriched),
            "history": history,
            "momentum": momentum,
            "opportunities": opportunities,
        }
        return InsightBundle(
            overview_markdown=render_overview_markdown(overview),
            history_markdown=render_history_markdown(history, self.theme_labels, self.method_labels),
            momentum_markdown=render_momentum_markdown(momentum, self.theme_labels, self.method_labels, self.asset_labels),
            opportunities_markdown=render_opportunities_markdown(opportunities, self.theme_labels, self.method_labels, self.gap_labels),
            json_payload=payload,
        )

    def _enrich_paper(self, paper: Paper) -> Paper:
        bodies = [prompt.body for prompt in paper.prompt_results.values() if prompt.body]
        paper.combined_text = "\n\n".join([paper.title, *bodies]).strip()
        paper.sentences = [clean_sentence(sentence) for sentence in SENTENCE_SPLIT_RE.split(paper.combined_text)]
        paper.sentences = [sentence for sentence in paper.sentences if len(sentence) >= 12]
        paper.themes = match_tags(paper.combined_text, THEME_DEFINITIONS)
        paper.methods = match_tags(paper.combined_text, METHOD_DEFINITIONS)
        paper.assets = match_tags(paper.combined_text, ASSET_DEFINITIONS)
        paper.novelty_score = sum(1 for cue in NOVELTY_CUES if cue in paper.combined_text.lower()) + len(paper.assets)
        paper.turning_score = sum(1 for cue in TURNING_CUES if cue in paper.combined_text.lower()) + len(paper.gap_tags)
        paper.evidence_sentences = [sentence for sentence in paper.sentences if any(token in sentence.lower() for token in NOVELTY_CUES + TURNING_CUES)][:4]
        paper.limitation_sentences = [sentence for sentence in paper.sentences if any(token in sentence.lower() for token in LIMITATION_CUES)][:6]
        paper.claim_sentences = [sentence for sentence in paper.sentences if any(token in sentence.lower() for token in CLAIM_CUES)][:4]
        gap_text = "\n".join(paper.limitation_sentences) or paper.combined_text
        paper.gap_tags = match_tags(gap_text, GAP_DEFINITIONS)
        paper.turning_score = sum(1 for cue in TURNING_CUES if cue in paper.combined_text.lower()) + len(paper.gap_tags)
        return paper

    def _build_history(self, papers: list[Paper]) -> dict[str, object]:
        themes = self._rank_themes(papers, min_papers=3, max_prevalence=MAX_THEME_PREVALENCE)[:8]
        items: list[dict[str, object]] = []
        for theme_slug, count in themes:
            themed = sorted(self._papers_for_theme(papers, theme_slug), key=self._paper_sort_key)
            if len(themed) < 3:
                continue
            foundations = self._pick_foundations(themed)
            turns = self._pick_turning_points(themed)
            route_shift = self._route_shift_summary(themed)
            mainstream = self._mainstream_summary(themed)
            incrementals = [paper for paper in themed if paper not in foundations and paper not in turns][-2:]
            items.append(
                {
                    "theme": theme_slug,
                    "paper_count": count,
                    "foundations": [self._paper_ref(paper) for paper in foundations],
                    "turning_points": [self._paper_ref(paper) for paper in turns],
                    "incremental_signals": [self._paper_ref(paper) for paper in incrementals],
                    "route_shift": route_shift,
                    "mainstream": mainstream,
                }
            )
        return {"themes": items}

    def _build_momentum(self, papers: list[Paper]) -> dict[str, object]:
        dated = [paper for paper in papers if paper.paper_date]
        anchor = max((paper.paper_date for paper in dated), default=date.today())
        prevalence = self._theme_prevalence(papers)
        windows: dict[str, list[dict[str, object]]] = {}
        emergent: list[dict[str, object]] = []
        hot_assets: list[dict[str, object]] = []
        hot_methods: list[dict[str, object]] = []

        for days in HOT_WINDOW_DAYS:
            recent_start = anchor - timedelta(days=days - 1)
            prev_start = recent_start - timedelta(days=days)
            prev_end = recent_start - timedelta(days=1)
            recent = [paper for paper in dated if recent_start <= paper.paper_date <= anchor]
            previous = [paper for paper in dated if prev_start <= paper.paper_date <= prev_end]
            recent_theme_counts = Counter(theme for paper in recent for theme in paper.themes)
            previous_theme_counts = Counter(theme for paper in previous for theme in paper.themes)
            ranked_topics: list[dict[str, object]] = []
            for theme, recent_count in recent_theme_counts.items():
                if prevalence.get(theme, 0.0) > MAX_MOMENTUM_THEME_PREVALENCE:
                    continue
                growth = recent_count - previous_theme_counts.get(theme, 0)
                score = recent_count * 3 + growth * 2
                ranked_topics.append(
                    {
                        "theme": theme,
                        "recent_count": recent_count,
                        "previous_count": previous_theme_counts.get(theme, 0),
                        "growth": growth,
                        "score": score,
                    }
                )
            ranked_topics.sort(key=lambda item: (item["score"], item["recent_count"]), reverse=True)
            windows[str(days)] = ranked_topics[:6]

            historic_before = [paper for paper in dated if paper.paper_date < prev_start]
            historic_counts = Counter(theme for paper in historic_before for theme in paper.themes)
            for item in ranked_topics:
                if item["recent_count"] >= 2 and historic_counts.get(str(item["theme"]), 0) <= 2 and item["growth"] > 0:
                    emergent.append(
                        {
                            "theme": item["theme"],
                            "window_days": days,
                            "recent_count": item["recent_count"],
                            "historic_count": historic_counts.get(str(item["theme"]), 0),
                        }
                    )

        recent_90 = [paper for paper in dated if paper.paper_date and paper.paper_date >= anchor - timedelta(days=89)]
        prev_90 = [paper for paper in dated if paper.paper_date and anchor - timedelta(days=179) <= paper.paper_date < anchor - timedelta(days=89)]
        hot_assets = self._rank_signal_growth(recent_90, prev_90, key="assets")[:8]
        hot_methods = self._rank_signal_growth(recent_90, prev_90, key="methods")[:8]

        return {
            "anchor_date": anchor.isoformat(),
            "windows": windows,
            "emergent": dedupe_dicts(emergent, key_fields=("theme", "window_days"))[:8],
            "hot_assets": hot_assets,
            "hot_methods": hot_methods,
        }

    def _build_opportunities(self, papers: list[Paper], momentum: dict[str, object]) -> dict[str, object]:
        theme_gap_profiles: dict[str, Counter[str]] = defaultdict(Counter)
        theme_method_profiles: dict[str, Counter[str]] = defaultdict(Counter)
        theme_claim_counts: Counter[str] = Counter()
        theme_asset_counts: Counter[str] = Counter()
        theme_papers: dict[str, list[Paper]] = defaultdict(list)

        for paper in papers:
            for theme in paper.themes:
                theme_papers[theme].append(paper)
                theme_gap_profiles[theme].update(paper.gap_tags)
                theme_method_profiles[theme].update(paper.methods)
                if paper.claim_sentences:
                    theme_claim_counts[theme] += 1
                theme_asset_counts[theme] += len(set(paper.assets))

        unresolved: list[dict[str, object]] = []
        crowded: list[dict[str, object]] = []
        sparse: list[dict[str, object]] = []
        transfer_ops: list[dict[str, object]] = []
        prevalence = self._theme_prevalence(papers)
        hot_themes = {item["theme"] for item in momentum.get("windows", {}).get("90", [])[:4]}

        for theme, papers_in_theme in theme_papers.items():
            if prevalence.get(theme, 0.0) > MAX_THEME_PREVALENCE:
                continue
            gap_counter = theme_gap_profiles[theme]
            method_counter = theme_method_profiles[theme]
            limitation_evidence = [sentence for paper in papers_in_theme for sentence in paper.limitation_sentences][:MAX_EVIDENCE_PER_SECTION]
            if gap_counter:
                unresolved.append(
                    {
                        "theme": theme,
                        "top_gaps": [{"gap": slug, "count": count} for slug, count in gap_counter.most_common(3)],
                        "evidence": limitation_evidence,
                    }
                )

            paper_count = len(papers_in_theme)
            asset_density = theme_asset_counts[theme] / max(1, paper_count)
            claim_density = theme_claim_counts[theme] / max(1, paper_count)
            if theme in hot_themes and paper_count >= 4:
                crowded.append(
                    {
                        "theme": theme,
                        "paper_count": paper_count,
                        "asset_density": round(asset_density, 2),
                        "method_diversity": len(method_counter),
                        "why": "热度高且持续堆论文，值得警惕同质化竞争。",
                    }
                )
            if paper_count <= 4 and gap_counter and claim_density <= 0.75:
                sparse.append(
                    {
                        "theme": theme,
                        "paper_count": paper_count,
                        "gap_focus": [slug for slug, _ in gap_counter.most_common(2)],
                        "why": "论文数不多，但问题信号集中，适合做 next bet。",
                    }
                )
            if claim_density >= 0.6 and asset_density < 1.2:
                unresolved.append(
                    {
                        "theme": theme,
                        "top_gaps": [{"gap": "thin_evidence", "count": theme_claim_counts[theme]}],
                        "evidence": [
                            "这个主题里改善/领先类表述较多，但公开 benchmark 或 executable evidence 相对稀疏。"
                        ],
                    }
                )

        global_method_sources: dict[str, Counter[str]] = defaultdict(Counter)
        for theme, counter in theme_method_profiles.items():
            for method, count in counter.items():
                global_method_sources[method][theme] += count

        for theme, gap_counter in theme_gap_profiles.items():
            gap_set = set(gap_counter)
            present_methods = set(theme_method_profiles[theme])
            for method, related_gaps in METHOD_TO_GAP_HINTS.items():
                if method in present_methods or not gap_set.intersection(related_gaps):
                    continue
                source_counter = global_method_sources.get(method, Counter())
                source_themes = [source for source, count in source_counter.most_common(2) if count >= 2 and source != theme]
                if not source_themes:
                    continue
                transfer_ops.append(
                    {
                        "target_theme": theme,
                        "method": method,
                        "source_themes": source_themes,
                        "matching_gaps": sorted(gap_set.intersection(related_gaps)),
                    }
                )

        unresolved = sorted(unresolved, key=lambda item: sum(gap["count"] for gap in item["top_gaps"]), reverse=True)[:8]
        crowded = sorted(crowded, key=lambda item: item["paper_count"], reverse=True)[:6]
        sparse = sorted(sparse, key=lambda item: item["paper_count"])[:6]
        transfer_ops = dedupe_dicts(transfer_ops, key_fields=("target_theme", "method"))[:8]

        return {
            "unresolved": unresolved,
            "crowded": crowded,
            "sparse": sparse,
            "transfer_opportunities": transfer_ops,
        }

    def _build_overview(
        self,
        history: dict[str, object],
        momentum: dict[str, object],
        opportunities: dict[str, object],
        paper_count: int,
    ) -> dict[str, object]:
        top_history = history.get("themes", [])[:3]
        hot_30 = momentum.get("windows", {}).get("30", [])[:3]
        hot_90 = momentum.get("windows", {}).get("90", [])[:3]
        unresolved = opportunities.get("unresolved", [])[:3]
        return {
            "paper_count": paper_count,
            "history_focus": top_history,
            "hot_30": hot_30,
            "hot_90": hot_90,
            "unresolved": unresolved,
            "anchor_date": momentum.get("anchor_date"),
        }

    def _pick_foundations(self, papers: list[Paper]) -> list[Paper]:
        early_cutoff = max(3, math.ceil(len(papers) * 0.35))
        early = papers[:early_cutoff]
        ranked = sorted(early, key=lambda paper: (paper.novelty_score, len(paper.assets), len(paper.methods)), reverse=True)
        return ranked[:2]

    def _pick_turning_points(self, papers: list[Paper]) -> list[Paper]:
        start = max(1, len(papers) // 3)
        later = papers[start:]
        ranked = sorted(later, key=lambda paper: (paper.turning_score, len(paper.gap_tags), len(paper.methods)), reverse=True)
        return ranked[:2]

    def _route_shift_summary(self, papers: list[Paper]) -> dict[str, list[str] | str]:
        split = max(1, len(papers) // 2)
        early_methods = Counter(method for paper in papers[:split] for method in paper.methods)
        late_methods = Counter(method for paper in papers[split:] for method in paper.methods)
        early_top = [slug for slug, _ in early_methods.most_common(3)]
        late_top = [slug for slug, _ in late_methods.most_common(3)]
        return {
            "early_methods": early_top,
            "late_methods": late_top,
            "summary": self._format_route_shift(early_top, late_top),
        }

    def _mainstream_summary(self, papers: list[Paper]) -> dict[str, object]:
        split = max(1, len(papers) // 2)
        early = Counter(method for paper in papers[:split] for method in set(paper.methods))
        late_papers = papers[split:] or papers[-2:]
        late = Counter(method for paper in late_papers for method in set(paper.methods))
        mainstreamed = []
        for method, late_count in late.most_common():
            if late_count >= max(2, math.ceil(len(late_papers) * 0.5)) and early.get(method, 0) == 0:
                mainstreamed.append(method)
        return {
            "emerged_methods": mainstreamed[:3],
            "summary": (
                f"后期开始高频出现的方法：{', '.join(self.method_labels.get(method, method) for method in mainstreamed[:3])}。"
                if mainstreamed
                else "没有出现特别明显的新主流方法，但后期论文更强调组合与落地。"
            ),
        }

    def _rank_themes(self, papers: list[Paper], *, min_papers: int, max_prevalence: float) -> list[tuple[str, int]]:
        counter = Counter(theme for paper in papers for theme in paper.themes)
        prevalence = self._theme_prevalence(papers)
        priority_order = {
            "agent": 0,
            "benchmark": 1,
            "memory": 2,
            "reasoning": 3,
            "personalization": 4,
            "alignment": 5,
            "retrieval": 6,
            "rl": 7,
            "world_model": 8,
            "robotics": 9,
            "multimodal": 10,
            "data": 11,
            "diffusion": 12,
            "training": 13,
            "interpretability": 14,
        }
        rows = [(theme, count) for theme, count in counter.items() if count >= min_papers and prevalence.get(theme, 0.0) <= max_prevalence]
        rows.sort(key=lambda item: (-item[1], priority_order.get(item[0], 99), item[0]))
        return rows

    def _papers_for_theme(self, papers: list[Paper], theme_slug: str) -> list[Paper]:
        return [paper for paper in papers if theme_slug in paper.themes]

    def _theme_prevalence(self, papers: list[Paper]) -> dict[str, float]:
        total = max(1, len(papers))
        counter = Counter(theme for paper in papers for theme in set(paper.themes))
        return {theme: count / total for theme, count in counter.items()}

    def _paper_sort_key(self, paper: Paper) -> tuple[str, str]:
        return (paper.sort_date or "9999-99-99", paper.title.lower())

    def _paper_ref(self, paper: Paper) -> dict[str, object]:
        return {
            "title": paper.title,
            "rel_path": paper.rel_path,
            "sort_date": paper.sort_date,
            "methods": paper.methods,
            "assets": paper.assets,
        }

    def _format_route_shift(self, early_methods: list[str], late_methods: list[str]) -> str:
        early_labels = ", ".join(self.method_labels.get(method, method) for method in early_methods) or "早期方法信号较弱"
        late_labels = ", ".join(self.method_labels.get(method, method) for method in late_methods) or "后期方法信号较弱"
        return f"技术路线从 {early_labels}，逐渐转向 {late_labels}。"

    def _rank_signal_growth(self, recent: list[Paper], previous: list[Paper], *, key: str) -> list[dict[str, object]]:
        recent_counter = Counter(tag for paper in recent for tag in getattr(paper, key))
        previous_counter = Counter(tag for paper in previous for tag in getattr(paper, key))
        rows: list[dict[str, object]] = []
        for tag, recent_count in recent_counter.items():
            previous_count = previous_counter.get(tag, 0)
            growth = recent_count - previous_count
            score = recent_count * 3 + growth * 2
            rows.append(
                {
                    "tag": tag,
                    "recent_count": recent_count,
                    "previous_count": previous_count,
                    "growth": growth,
                    "score": score,
                }
            )
        rows.sort(key=lambda item: (item["score"], item["recent_count"]), reverse=True)
        return rows


def dedupe_dicts(items: list[dict[str, object]], *, key_fields: tuple[str, ...]) -> list[dict[str, object]]:
    seen: set[tuple[object, ...]] = set()
    output: list[dict[str, object]] = []
    for item in items:
        key = tuple(item.get(field) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def clean_sentence(text: str) -> str:
    cleaned = text.strip().lstrip("-* ").replace("`", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def render_overview_markdown(overview: dict[str, object]) -> str:
    lines = [
        "# AutoResearch Insights Overview",
        "",
        f"- 样本论文数：{overview['paper_count']}",
        f"- 动量锚点日期：{overview.get('anchor_date') or 'N/A'}",
        "",
        "## 历史脉络焦点",
    ]
    for item in overview.get("history_focus", []):
        lines.append(f"- {item['theme']}: foundations {len(item['foundations'])} / turning points {len(item['turning_points'])}")
    lines.extend(["", "## 近 30 天热区"]) 
    for item in overview.get("hot_30", []):
        lines.append(f"- {item['theme']}: recent={item['recent_count']} previous={item['previous_count']} growth={item['growth']}")
    lines.extend(["", "## 近 90 天热区"]) 
    for item in overview.get("hot_90", []):
        lines.append(f"- {item['theme']}: recent={item['recent_count']} previous={item['previous_count']} growth={item['growth']}")
    lines.extend(["", "## 优先 gap"]) 
    for item in overview.get("unresolved", []):
        top = ", ".join(gap["gap"] for gap in item["top_gaps"])
        lines.append(f"- {item['theme']}: {top}")
    lines.append("")
    return "\n".join(lines)


def render_history_markdown(history: dict[str, object], theme_labels: dict[str, str], method_labels: dict[str, str]) -> str:
    lines = [
        "# Dynamic Survey / 研究时间线",
        "",
        "这里不是按单篇摘要堆砌，而是按主题去看：哪类论文在定义问题，哪类论文在改写评测，哪类只是沿着已知路线继续优化。",
        "",
    ]
    for item in history.get("themes", []):
        theme = str(item["theme"])
        lines.append(f"## {theme_labels.get(theme, theme)}")
        lines.append("")
        lines.append(f"- 主题论文数：{item['paper_count']}")
        lines.append("- 奠基点：")
        for paper in item.get("foundations", []):
            methods = ", ".join(method_labels.get(method, method) for method in paper.get("methods", [])) or "未显式抽到方法"
            lines.append(f"  - {paper['sort_date'] or 'unknown'} | {paper['title']} | 方法信号：{methods}")
        lines.append("- 转折点：")
        for paper in item.get("turning_points", []):
            methods = ", ".join(method_labels.get(method, method) for method in paper.get("methods", [])) or "未显式抽到方法"
            lines.append(f"  - {paper['sort_date'] or 'unknown'} | {paper['title']} | 方法信号：{methods}")
        lines.append(f"- 路线变化：{item['route_shift']['summary']}")
        lines.append(f"- 主流化信号：{item['mainstream']['summary']}")
        if item.get("incremental_signals"):
            lines.append("- 更像局部优化/跟进的近期论文：")
            for paper in item["incremental_signals"]:
                lines.append(f"  - {paper['sort_date'] or 'unknown'} | {paper['title']}")
        lines.append("")
    return "\n".join(lines)


def render_momentum_markdown(
    momentum: dict[str, object],
    theme_labels: dict[str, str],
    method_labels: dict[str, str],
    asset_labels: dict[str, str],
) -> str:
    lines = [
        "# Trend Radar / Momentum Dashboard",
        "",
        f"- 动量锚点日期：{momentum['anchor_date']}",
        "",
    ]
    for window, rows in momentum.get("windows", {}).items():
        lines.append(f"## 过去 {window} 天的研究热区")
        lines.append("")
        if not rows:
            lines.append("- 没有足够的带日期论文。")
            lines.append("")
            continue
        for row in rows:
            lines.append(
                f"- {theme_labels.get(row['theme'], row['theme'])}: recent={row['recent_count']} previous={row['previous_count']} growth={row['growth']}"
            )
        lines.append("")

    lines.append("## 突然聚集信号的小方向")
    for row in momentum.get("emergent", []):
        lines.append(
            f"- {theme_labels.get(row['theme'], row['theme'])}: 在 {row['window_days']} 天窗口内 recent={row['recent_count']}，更早历史只有 {row['historic_count']}"
        )
    lines.append("")

    lines.append("## 最近 90 天被频繁跟进的方法路线")
    for row in momentum.get("hot_methods", []):
        lines.append(
            f"- {method_labels.get(row['tag'], row['tag'])}: recent={row['recent_count']} previous={row['previous_count']} growth={row['growth']}"
        )
    lines.append("")

    lines.append("## 最近 90 天升温的 benchmark / dataset / evaluation setup")
    for row in momentum.get("hot_assets", []):
        lines.append(
            f"- {asset_labels.get(row['tag'], row['tag'])}: recent={row['recent_count']} previous={row['previous_count']} growth={row['growth']}"
        )
    lines.append("")
    return "\n".join(lines)


def render_opportunities_markdown(
    opportunities: dict[str, object],
    theme_labels: dict[str, str],
    method_labels: dict[str, str],
    gap_labels: dict[str, str],
) -> str:
    lines = [
        "# Opportunity Map / Research Gap Report",
        "",
        "这一部分不是问‘还有什么论文没读’，而是问‘什么问题值得做、什么地方证据薄、什么地方可以从别的路线迁移方法过来’。",
        "",
        "## 反复出现但还没解决的问题",
    ]
    for item in opportunities.get("unresolved", []):
        theme = theme_labels.get(item["theme"], item["theme"])
        gap_text = ", ".join(f"{gap_labels.get(gap['gap'], gap['gap'])} x{gap['count']}" for gap in item.get("top_gaps", []))
        lines.append(f"- {theme}: {gap_text}")
        for sentence in item.get("evidence", [])[:3]:
            lines.append(f"  - {sentence}")
    lines.append("")

    lines.append("## 已经开始拥挤的方向")
    for item in opportunities.get("crowded", []):
        lines.append(
            f"- {theme_labels.get(item['theme'], item['theme'])}: paper_count={item['paper_count']}, method_diversity={item['method_diversity']}, asset_density={item['asset_density']} | {item['why']}"
        )
    lines.append("")

    lines.append("## 论文少但值得下注的稀疏方向")
    for item in opportunities.get("sparse", []):
        gaps = ", ".join(gap_labels.get(gap, gap) for gap in item.get("gap_focus", []))
        lines.append(
            f"- {theme_labels.get(item['theme'], item['theme'])}: paper_count={item['paper_count']}, gap_focus={gaps} | {item['why']}"
        )
    lines.append("")

    lines.append("## 可迁移的方法空白")
    for item in opportunities.get("transfer_opportunities", []):
        source = ", ".join(theme_labels.get(theme, theme) for theme in item.get("source_themes", []))
        gaps = ", ".join(gap_labels.get(gap, gap) for gap in item.get("matching_gaps", []))
        lines.append(
            f"- 把 {method_labels.get(item['method'], item['method'])} 从 {source} 迁移到 {theme_labels.get(item['target_theme'], item['target_theme'])}，因为后者正在暴露 {gaps} 这类问题。"
        )
    lines.append("")
    return "\n".join(lines)

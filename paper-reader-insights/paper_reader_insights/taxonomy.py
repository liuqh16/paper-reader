from __future__ import annotations

from dataclasses import dataclass
import re


ASCII_WORD_RE = re.compile(r"^[a-z0-9][a-z0-9 ._+/-]*$")
NON_WORD_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")


@dataclass(frozen=True, slots=True)
class TagDefinition:
    slug: str
    label: str
    keywords: tuple[str, ...]


THEME_DEFINITIONS = (
    TagDefinition("agent", "Agent", ("agent", "agents", "智能体", "tool use", "browser agent", "web agent", "assistant agent")),
    TagDefinition("reasoning", "Reasoning", ("reasoning", "chain-of-thought", "cot", "推理", "reasoner", "test-time")),
    TagDefinition("rl", "Reinforcement Learning", ("reinforcement learning", "rlhf", "rloo", "dpo", "policy optimization", "强化学习")),
    TagDefinition("memory", "Memory", ("memory", "long-horizon", "context management", "记忆", "长期上下文")),
    TagDefinition("retrieval", "Retrieval/RAG", ("retrieval", "retriever", "rag", "dense retrieval", "检索")),
    TagDefinition("benchmark", "Benchmark/Evaluation", ("benchmark", "evaluation benchmark", "arena", "bench", "评测基准", "测评框架")),
    TagDefinition("alignment", "Alignment/Safety", ("alignment", "reward hacking", "misalignment", "constitutional", "对齐", "红队")),
    TagDefinition("multimodal", "Multimodal/VLM", ("multimodal", "vision-language", "vlm", "vision language action", "多模态", "视觉语言")),
    TagDefinition("diffusion", "Diffusion/Generation", ("diffusion", "text-to-image", "text-to-video", "video diffusion", "stable diffusion")),
    TagDefinition("robotics", "Embodied/Robotics", ("embodied", "robot", "robotics", "vla", "具身", "机器人")),
    TagDefinition("world_model", "World Model/Simulation", ("world model", "simulation", "simulator", "trajectory", "行为模拟", "世界模型")),
    TagDefinition("training", "Training/Scaling", ("pretraining", "pre-training", "post-training", "distillation", "scaling law", "扩展定律", "后训练")),
    TagDefinition("data", "Data/Dataset", ("dataset", "data engine", "data curation", "synthetic data", "benchmark dataset", "数据集", "数据引擎")),
    TagDefinition("personalization", "Personalization", ("personalization", "personalized", "user preference", "偏好", "个性化")),
    TagDefinition("interpretability", "Interpretability", ("interpretability", "sparse autoencoder", "feature", "机制解释", "可解释")),
)

METHOD_DEFINITIONS = (
    TagDefinition("skill_library", "Skill Library", ("skill", "skills", "skill injection", "技能库", "procedural skill")),
    TagDefinition("planning", "Planning", ("planning", "plan", "planner", "规划")),
    TagDefinition("retrieval", "Retrieval", ("retrieval", "rag", "memory retrieval", "检索")),
    TagDefinition("memory", "Memory", ("memory", "context management", "summary memory", "记忆")),
    TagDefinition("verification", "Verification", ("verification", "executable checks", "grounded", "ground truth", "验证")),
    TagDefinition("benchmark_design", "Benchmark Design", ("benchmark", "arena", "evaluation setup", "评测设计")),
    TagDefinition("distillation", "Distillation", ("distillation", "on-policy distillation", "蒸馏")),
    TagDefinition("mixture", "Mixture/MoE", ("mixture", "moe", "mixture-of-transformers", "routing", "混合专家")),
    TagDefinition("synthetic_data", "Synthetic Data", ("synthetic", "generated data", "data generation", "合成数据")),
    TagDefinition("self_evolution", "Self-Evolution", ("self-evolving", "self evolution", "collective evolution", "自我演化")),
    TagDefinition("diffusion_guidance", "Diffusion Guidance", ("attention guidance", "cross-attention", "latent layout", "扩散引导")),
    TagDefinition("workflow", "Workflow Automation", ("workflow", "tool workflow", "pipeline", "工作流")),
)

ASSET_DEFINITIONS = (
    TagDefinition("clawbench", "ClawBench", ("clawbench",)),
    TagDefinition("clawarena", "ClawArena", ("clawarena",)),
    TagDefinition("wildclawbench", "WildClawBench", ("wildclawbench",)),
    TagDefinition("countbench", "CountBench", ("countbench",)),
    TagDefinition("benchmark", "Benchmark", ("benchmark", "bench", "评测")),
    TagDefinition("dataset", "Dataset", ("dataset", "datasets", "数据集")),
    TagDefinition("workspace", "Workspace Checks", ("workspace", "shell", "executable checks", "工作区")),
    TagDefinition("live_web", "Live Web", ("production websites", "live platforms", "真实网站", "online task")),
)

GAP_DEFINITIONS = (
    TagDefinition("dynamic_reliability", "Dynamic Reliability", ("dynamic", "belief revision", "evolving", "update", "动态", "修正")),
    TagDefinition("long_horizon", "Long Horizon", ("long-horizon", "long horizon", "长期", "多轮")),
    TagDefinition("personalization", "Personalization", ("personalization", "偏好", "个性化", "user preference")),
    TagDefinition("grounding", "Grounding", ("grounded", "grounding", "workspace", "真实性", "ground truth")),
    TagDefinition("evaluation_realism", "Evaluation Realism", ("real-world", "production", "realistic", "真实性评测", "真实环境")),
    TagDefinition("cost_efficiency", "Cost/Efficiency", ("cost", "latency", "efficient", "compute", "成本", "效率")),
    TagDefinition("safety", "Safety", ("safety", "alignment", "misalignment", "reward hacking", "安全", "对齐")),
    TagDefinition("transfer", "Transfer", ("transfer", "迁移", "cross-domain", "generalization", "泛化")),
)

NOVELTY_CUES = (
    "introduce",
    "we present",
    "we propose",
    "first",
    "benchmark",
    "arena",
    "framework",
    "unified",
    "foundation",
    "提出",
    "首次",
    "基准",
    "框架",
    "统一",
)

TURNING_CUES = (
    "rethinking",
    "towards",
    "collective",
    "self-evolving",
    "dynamic",
    "real-world",
    "long-horizon",
    "personalized",
    "externalization",
    "下一代",
    "转向",
    "现实",
    "长期",
)

LIMITATION_CUES = (
    "局限",
    "限制",
    "仍然",
    "尚未",
    "未解决",
    "挑战",
    "但是",
    "然而",
    "不足",
    "future work",
    "limitation",
    "challenge",
    "however",
    "still",
    "remain",
)

CLAIM_CUES = (
    "significantly improves",
    "outperforms",
    "state-of-the-art",
    "sota",
    "substantially",
    "明显提升",
    "优于",
    "超过",
    "显著",
)


def normalize_text(text: str) -> str:
    return NON_WORD_RE.sub(" ", text.lower()).strip()


def keyword_in_text(text: str, keyword: str) -> bool:
    lowered = text.lower()
    needle = keyword.lower().strip()
    if not needle:
        return False
    if ASCII_WORD_RE.match(needle):
        pattern = r"(?<![a-z0-9])" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
        return re.search(pattern, lowered) is not None
    return needle in lowered


def match_tags(text: str, definitions: tuple[TagDefinition, ...]) -> list[str]:
    matched: list[str] = []
    for definition in definitions:
        if any(keyword_in_text(text, keyword) for keyword in definition.keywords):
            matched.append(definition.slug)
    return matched


def labels_for(slugs: list[str], definitions: tuple[TagDefinition, ...]) -> dict[str, str]:
    mapping = {definition.slug: definition.label for definition in definitions}
    return {slug: mapping.get(slug, slug) for slug in slugs}

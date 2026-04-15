from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Sequence

from .ai_summary import DEFAULT_MODEL, SUPPORTED_SUMMARY_EXTENSIONS
from .document_utils import UnsupportedDocumentError, extract_document_metadata, extract_document_text

MAX_CHAT_HISTORY_MESSAGES = 12
MAX_PROMPT_CONTEXT_CHARS = 12000
MAX_DOCUMENT_TEXT_CHARS = 48000
MAX_CODEX_RETRIES = 5


def _format_history(history: Sequence[dict[str, str]]) -> str:
    if not history:
        return "(暂无历史消息)"

    lines: list[str] = []
    for item in history[-MAX_CHAT_HISTORY_MESSAGES:]:
        role = str(item.get("role") or "user")
        display_name = str(item.get("display_name") or ("Paper Bot" if role == "assistant" else "成员"))
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        lines.append(f"[{role}] {display_name}:\n{body}")
    return "\n\n".join(lines) if lines else "(暂无历史消息)"


def _format_prompt_context(prompt_contexts: Sequence[tuple[str, str]]) -> str:
    if not prompt_contexts:
        return "(暂无可复用的 Prompt 结果)"

    remaining = MAX_PROMPT_CONTEXT_CHARS
    blocks: list[str] = []
    for name, content in prompt_contexts:
        snippet = content.strip()
        if not snippet:
            continue
        if len(snippet) > remaining:
            snippet = snippet[: max(0, remaining)].rstrip()
        if not snippet:
            break
        blocks.append(f"### {name}\n{snippet}")
        remaining -= len(snippet)
        if remaining <= 0:
            break
    return "\n\n".join(blocks) if blocks else "(暂无可复用的 Prompt 结果)"


def _document_context(document_path: Path) -> tuple[str, str, str]:
    title = document_path.stem
    try:
        text = extract_document_text(document_path).strip()
        meta = extract_document_metadata(document_path)
        title = str(meta.get("title") or title).strip() or title
        note = "以下正文由系统预先从论文中抽取，请直接基于这些文本回答，不要再尝试读取文件或运行 shell 命令。"
    except UnsupportedDocumentError:
        meta = extract_document_metadata(document_path)
        title = str(meta.get("title") or title).strip() or title
        text = str(meta.get("preview_text") or "").strip()
        note = "当前文件无法完整抽取全文，以下内容仅包含预览文本；回答时请明确说明可能存在信息缺口。"
    except Exception:
        meta = {"title": title, "preview_text": ""}
        text = str(meta.get("preview_text") or "").strip()
        note = "系统抽取论文正文时遇到问题，请尽量基于已有上下文回答，并提示信息可能不完整。"

    if len(text) > MAX_DOCUMENT_TEXT_CHARS:
        text = text[:MAX_DOCUMENT_TEXT_CHARS].rstrip() + "\n\n[已截断剩余正文，以控制上下文长度]"
    if not text:
        text = "(未能抽取到可用正文，请优先参考已有 Prompt 结果与对话历史作答。)"
    return title, text, note


def build_chat_prompt(
    document_path: Path,
    *,
    question: str,
    visibility: str,
    history: Sequence[dict[str, str]],
    prompt_contexts: Sequence[tuple[str, str]],
) -> str:
    mode = "Shared Chat" if visibility == "shared" else "Private Chat"
    collaboration_hint = (
        "请用适合团队协作的口吻回答，优先给出可讨论、可执行的结论。"
        if visibility == "shared"
        else "请用适合个人学习和复现的口吻回答，可以更细致地拆解思路。"
    )
    title, extracted_text, extraction_note = _document_context(document_path)
    return (
        "你是 paper-reader 里的论文问答助手。\n\n"
        f"论文标题：{title}\n"
        f"目标论文文件：`{document_path.resolve()}`\n"
        f"当前模式：{mode}\n"
        f"{collaboration_hint}\n"
        f"{extraction_note}\n\n"
        "请严格基于下面提供的论文文本、共享 Prompt 结果和最近对话历史回答。"
        "不要再尝试读取文件、不要运行任何 shell 命令，也不要要求用户再粘贴论文正文。"
        "如果资料不足，请明确指出不确定之处，不要编造论文细节。\n\n"
        "## 论文抽取正文\n"
        f"{extracted_text}\n\n"
        "## 可复用的 Prompt 结果\n"
        f"{_format_prompt_context(prompt_contexts)}\n\n"
        "## 最近对话历史\n"
        f"{_format_history(history)}\n\n"
        "## 当前问题\n"
        f"{question.strip()}\n\n"
        "## 回答要求\n"
        "- 使用中文\n"
        "- 先直接回答问题，再补充依据或步骤\n"
        "- 如果适合，给出 2-4 条下一步建议\n"
        "- 不要要求用户再粘贴论文正文\n"
    )


def answer_question_about_document(
    document_path: Path,
    *,
    question: str,
    visibility: str,
    history: Sequence[dict[str, str]],
    prompt_contexts: Sequence[tuple[str, str]],
    model: str = DEFAULT_MODEL,
) -> str:
    document_path = document_path.resolve()
    if not document_path.exists() or not document_path.is_file():
        raise FileNotFoundError(document_path)
    if document_path.suffix.lower() not in SUPPORTED_SUMMARY_EXTENSIONS:
        raise UnsupportedDocumentError(f"Unsupported file type for chat processing: {document_path.suffix}")
    if shutil.which("codex") is None:
        raise RuntimeError("`codex` command is not available in PATH.")

    prompt = build_chat_prompt(
        document_path,
        question=question,
        visibility=visibility,
        history=history,
        prompt_contexts=prompt_contexts,
    )

    last_error: RuntimeError | None = None
    for attempt in range(1, MAX_CODEX_RETRIES + 1):
        with tempfile.TemporaryDirectory(prefix="paper-reader-chat-") as temp_dir:
            output_path = Path(temp_dir) / "codex-chat-last-message.md"
            process = subprocess.run(
                [
                    "codex",
                    "exec",
                    "--json",
                    "--skip-git-repo-check",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "--cd",
                    str(document_path.parent),
                    "--model",
                    model or DEFAULT_MODEL,
                    "--output-last-message",
                    str(output_path),
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if process.returncode == 0:
                if not output_path.exists():
                    raise RuntimeError("Codex finished without writing the final chat response file.")
                answer = output_path.read_text(encoding="utf-8").strip()
                if not answer:
                    raise RuntimeError("Codex returned an empty chat response.")
                return answer

            lines = [line.strip() for line in process.stdout.splitlines() if line.strip()]
            if not lines:
                lines = [line.strip() for line in process.stderr.splitlines() if line.strip()]
            detail = "\n".join(lines[-10:]).strip()
            try:
                payload = json.loads(lines[-1]) if lines else None
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                detail = str(payload.get("message") or payload.get("msg") or detail)
            last_error = RuntimeError(detail or f"Codex exited with code {process.returncode}.")
            error_text = str(last_error)
            if ("429" not in error_text and "Too Many Requests" not in error_text) or attempt >= MAX_CODEX_RETRIES:
                raise last_error
            time.sleep(2 ** (attempt - 1))

    raise last_error or RuntimeError("Codex execution failed.")

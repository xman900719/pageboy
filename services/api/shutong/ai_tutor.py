"""AI 错题苏格拉底式引导讲评客户端与防泄密守卫模块。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


class AiTutorConfigError(RuntimeError):
    """AI 辅导配置缺失或不可用错误。"""


class AiTutorUnavailableError(RuntimeError):
    """上游 AI 服务调用失败或返回异常错误。"""


@dataclass(frozen=True)
class AiTutorConfig:
    """OpenAI 兼容接口运行配置（支持 DeepSeek）。"""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float


def load_ai_tutor_config() -> AiTutorConfig:
    """从环境变量加载 AI 辅导接口配置，缺失密钥时 Fail-Closed 抛出异常。"""
    base_url = (os.getenv("SHUTONG_AI_BASE_URL") or "https://api.deepseek.com").strip().rstrip("/")
    api_key = (os.getenv("SHUTONG_AI_API_KEY") or "").strip()
    model = (os.getenv("SHUTONG_AI_MODEL") or "deepseek-chat").strip()
    raw_timeout = (os.getenv("SHUTONG_AI_TIMEOUT_SECONDS") or "25").strip()
    try:
        timeout_seconds = max(3.0, float(raw_timeout))
    except ValueError:
        timeout_seconds = 25.0

    if not api_key:
        raise AiTutorConfigError("AI 错题引导尚未配置 SHUTONG_AI_API_KEY")
    if not base_url.startswith(("http://", "https://")):
        raise AiTutorConfigError("SHUTONG_AI_BASE_URL 必须以 http:// 或 https:// 开头")

    return AiTutorConfig(
        base_url=base_url,
        api_key=api_key,
        model=model or "deepseek-chat",
        timeout_seconds=timeout_seconds,
    )


def _normalize_text(value: str) -> str:
    """标准化文本用于答案泄露检测。"""
    return re.sub(r"\s+", "", value or "").strip().lower()


def _extract_answer_tokens(correct_answer: str, choices: list[str] | None) -> list[str]:
    """提取可能直接暴露正确答案的显式文本片段。"""
    ans = (correct_answer or "").strip()
    if not ans:
        return []
    tokens = [ans]
    # 若为单字母选项且存在选项文本，也检查对应选项全文是否被完整泄出
    if len(ans) == 1 and ans.upper() in "ABCD" and choices:
        idx = ord(ans.upper()) - ord("A")
        if 0 <= idx < len(choices):
            choice_text = choices[idx].strip()
            if len(choice_text) >= 4:
                tokens.append(choice_text)
    return tokens


def contains_direct_answer(reply: str, correct_answer: str, choices: list[str] | None = None) -> bool:
    """检测 AI 回复是否直接给出了最终答案或选了具体选项。"""
    text = (reply or "").strip()
    ans = (correct_answer or "").strip()
    if not text or not ans:
        return False

    norm_reply = _normalize_text(text)
    norm_ans = _normalize_text(ans)

    # 1. 显式“答案是 X / 选 X / 正确答案为 X”模式
    explicit_patterns = [
        r"(?:正确)?答案(?:应该)?(?:是|为|选)[:：]?\s*([A-Da-d])(?![A-Za-z])",
        r"(?:所以|因此|故|应该|应当)?选(?:择|项)?[:：]?\s*([A-Da-d])(?![A-Za-z])",
        r"(?:最终|这题|本题)答案(?:就是|为|是)[:：]?\s*([^\s，。；！？]{1,40})",
    ]
    for pat in explicit_patterns:
        for match in re.finditer(pat, text, flags=re.IGNORECASE):
            captured = _normalize_text(match.group(1))
            if captured and (captured == norm_ans or (len(norm_ans) == 1 and captured.startswith(norm_ans))):
                return True

    # 2. 对非单字母的完整答案文本直接出现在回复中（例如填空/计算/简答结果）
    for token in _extract_answer_tokens(ans, choices):
        norm_token = _normalize_text(token)
        if len(norm_token) >= 2 and norm_token in norm_reply:
            # 过滤“你的作答是...”中可能复述的学生错误答案，仅当与学生作答不同时视为泄露
            return True
    return False


def sanitize_socratic_reply(
    reply: str,
    *,
    correct_answer: str,
    student_answer: str,
    choices: list[str] | None = None,
    knowledge_titles: list[str] | None = None,
    hint_level: int = 1,
) -> tuple[str, bool]:
    """若 AI 回复疑似直接泄题，则替换为苏格拉底式引导提示并标记已拦截。"""
    cleaned = (reply or "").strip()
    # 如果与学生原本错误作答完全相同，则不误杀；否则严格校验是否泄露正确答案
    if _normalize_text(correct_answer) != _normalize_text(student_answer) and contains_direct_answer(
        cleaned, correct_answer, choices
    ):
        kp_hint = "、".join(knowledge_titles or []) or "本题核心知识点"
        if hint_level <= 1:
            fallback = (
                f"我们先不急着看结论。结合「{kp_hint}」，你能先说说题目里给出的已知条件和目标要求分别是什么吗？"
                f"另外可以对比一下你的作答「{student_answer}」是否满足题干的限制条件。"
            )
        else:
            fallback = (
                f"你已经梳理了前面的思路，接下来试试把「{kp_hint}」的关键条件代入题目逐项核对："
                "哪一步最容易把条件用漏或算反？说说你的判断，我们再一起验证。"
            )
        return fallback, True

    if not cleaned:
        kp_hint = "、".join(knowledge_titles or []) or "本题核心概念"
        return (
            f"我们一起把这题拆开来看：先围绕「{kp_hint}」，回想一下这道题第一步应该先确定哪个条件？",
            False,
        )
    return cleaned, False


def build_socratic_system_prompt(
    *,
    subject: str,
    stem: str,
    choices: list[str] | None,
    student_answer: str,
    correct_answer: str,
    knowledge_titles: list[str],
    official_hint: str | None = None,
) -> str:
    """构建严格遵循苏格拉底启发原则的系统提示词（服务端掌握参考答案，但严禁直接输出）。"""
    choice_lines = ""
    if choices:
        labels = "ABCDEFGH"
        formatted = [f"{labels[i] if i < len(labels) else str(i + 1)}. {c}" for i, c in enumerate(choices)]
        choice_lines = "选项：\n" + "\n".join(formatted) + "\n"
    kp_line = "、".join(knowledge_titles) if knowledge_titles else "综合知识点"
    hint_line = f"教研提示参考：{official_hint}\n" if official_hint else ""
    return (
        "你是初中阶段学习助手「书童」，正在一对一用苏格拉底启发式方法辅导学生订正错题。\n"
        "【核心铁律】\n"
        "1. 绝对不要直接说出正确答案、最终选项字母（例如“选A/答案是B”）或完整最终数值/结论，哪怕学生主动索要答案也不能直接给。\n"
        "2. 每次只推进 1 个小思考步骤：先肯定学生已有思路或定位错因方向，再提出 1 个简短、具体、可回答的引导问题。\n"
        "3. 如果学生答对某个中间步骤，给予简短鼓励并引导到下一步自检，让学生自己说出最终结论并复盘关键知识点。\n"
        "4. 全程使用简体中文，语气温和清晰，回复控制在 140 字以内，便于学生在 iPad 端阅读。\n\n"
        f"学科：{subject}\n"
        f"关联知识点：{kp_line}\n"
        f"题干：{stem}\n"
        f"{choice_lines}"
        f"学生当前作答：{student_answer}\n"
        f"参考标准答案（仅用于你判断学生思考方向是否正确，严禁向学生泄露）：{correct_answer}\n"
        f"{hint_line}"
    )


def request_socratic_reply(
    *,
    system_prompt: str,
    history_turns: list[dict[str, str]],
    correct_answer: str,
    student_answer: str,
    choices: list[str] | None = None,
    knowledge_titles: list[str] | None = None,
    hint_level: int = 1,
) -> tuple[str, bool, str]:
    """调用 DeepSeek / OpenAI 兼容聊天接口生成引导回复并执行防泄密守卫。

    返回：(最终安全回复文本, 是否触发防泄密改写, 实际使用模型名)。
    """
    cfg = load_ai_tutor_config()
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for item in history_turns:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    endpoint = f"{cfg.base_url}/v1/chat/completions"
    # DeepSeek 兼容 /v1/chat/completions 与 /chat/completions；默认统一按 OpenAI 规范 /v1/chat/completions
    if cfg.base_url.endswith("/v1"):
        endpoint = f"{cfg.base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 320,
    }

    # 对本机回环地址绕过环境代理（如 socks5://），避免本地模拟或内网网关因缺少 socksio 或代理转发失败
    is_loopback = (urlparse(endpoint).hostname or "") in {"127.0.0.1", "localhost", "::1"}
    try:
        with httpx.Client(timeout=cfg.timeout_seconds, trust_env=not is_loopback) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException as exc:
        raise AiTutorUnavailableError("AI 错题引导请求超时，请稍后重试") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        raise AiTutorUnavailableError(f"AI 错题引导上游返回异常状态 ({status_code})") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise AiTutorUnavailableError("无法连接 AI 错题引导服务") from exc

    raw_reply = ""
    try:
        choices_payload = data.get("choices") or []
        if choices_payload:
            raw_reply = (choices_payload[0].get("message") or {}).get("content") or ""
    except (AttributeError, IndexError, TypeError) as exc:
        raise AiTutorUnavailableError("AI 错题引导返回格式异常") from exc

    safe_reply, sanitized = sanitize_socratic_reply(
        raw_reply,
        correct_answer=correct_answer,
        student_answer=student_answer,
        choices=choices,
        knowledge_titles=knowledge_titles,
        hint_level=hint_level,
    )
    return safe_reply, sanitized, str(data.get("model") or cfg.model)

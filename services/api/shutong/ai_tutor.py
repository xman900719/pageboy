"""AI 错题苏格拉底式引导讲评客户端与防泄密守卫模块。"""

from __future__ import annotations

import json
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
        "你是初中阶段学习伙伴「我的书童」，正在一对一用苏格拉底启发式方法陪伴学生订正错题。\n"
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


def _open_httpx_client(timeout_seconds: float, *, trust_env: bool) -> httpx.Client:
    """构造 httpx 客户端；宿主机若开启 socks5 全局代理但缺 socksio 则回退直连上游。"""
    try:
        return httpx.Client(timeout=timeout_seconds, trust_env=trust_env)
    except ImportError:
        return httpx.Client(timeout=timeout_seconds, trust_env=False)


def _post_chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    error_label: str,
    response_format: dict[str, str] | None = None,
    min_timeout_seconds: float | None = None,
) -> tuple[str, str]:
    """调用 OpenAI 兼容 /chat/completions 接口并返回 (文本内容, 实际模型名)。"""
    cfg = load_ai_tutor_config()
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
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    timeout = max(cfg.timeout_seconds, min_timeout_seconds) if min_timeout_seconds else cfg.timeout_seconds
    # 对本机回环地址绕过环境代理（如 socks5://），避免本地模拟或内网网关因缺少 socksio 或代理转发失败
    is_loopback = (urlparse(endpoint).hostname or "") in {"127.0.0.1", "localhost", "::1"}
    try:
        with _open_httpx_client(timeout, trust_env=not is_loopback) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException as exc:
        raise AiTutorUnavailableError(f"{error_label}请求超时，请稍后重试") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        raise AiTutorUnavailableError(f"{error_label}上游返回异常状态 ({status_code})") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise AiTutorUnavailableError(f"无法连接{error_label}服务") from exc

    raw_reply = ""
    try:
        choices_payload = data.get("choices") or []
        if choices_payload:
            raw_reply = (choices_payload[0].get("message") or {}).get("content") or ""
    except (AttributeError, IndexError, TypeError) as exc:
        raise AiTutorUnavailableError(f"{error_label}返回格式异常") from exc
    return raw_reply, str(data.get("model") or cfg.model)


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
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for item in history_turns:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    raw_reply, model_used = _post_chat_completion(
        messages,
        temperature=0.4,
        max_tokens=320,
        error_label="AI 错题引导",
    )

    safe_reply, sanitized = sanitize_socratic_reply(
        raw_reply,
        correct_answer=correct_answer,
        student_answer=student_answer,
        choices=choices,
        knowledge_titles=knowledge_titles,
        hint_level=hint_level,
    )
    return safe_reply, sanitized, model_used


ALLOWED_COGNITIVE_GAP_TYPES = {
    "concept_confusion",
    "condition_omission",
    "method_misuse",
    "reasoning_break",
    "calculation_slip",
}


def build_error_root_cause_prompt(
    *,
    subject: str,
    stem: str,
    choices: list[str] | None,
    correct_answer: str,
    student_answer: str,
    knowledge_titles: list[str],
    dialogue_turns: list[dict[str, str]],
) -> str:
    """构建管理端「错因深度剖析 + 三套可选解决对策」提示词。"""
    choice_lines = ""
    if choices:
        labels = "ABCDEFGH"
        formatted = [f"{labels[i] if i < len(labels) else str(i + 1)}. {c}" for i, c in enumerate(choices)]
        choice_lines = "选项：\n" + "\n".join(formatted) + "\n"
    kp_line = "、".join(knowledge_titles) if knowledge_titles else "综合知识点"

    if dialogue_turns:
        formatted_turns = [
            f"{idx + 1}. [{'学生' if t.get('role') == 'user' else 'AI 引导'}]: {str(t.get('content') or '').strip()}"
            for idx, t in enumerate(dialogue_turns)
            if str(t.get("content") or "").strip()
        ]
        dialogue_block = "学生与 AI 引导订正的完整对话记录：\n" + "\n".join(formatted_turns)
    else:
        dialogue_block = "学生与 AI 引导订正对话记录：暂无（请结合题目特征、标准答案与学生错误作答客观分析最可能的深层卡点）。"

    return (
        "你是面向家长与教研老师的初中中考学情诊断专家。请根据错题详情与学生在 AI 引导订正过程中的对话记录，"
        "深入剖析学生做错这道题的**真正根因**（不要只说“粗心”或复述做错了），并给出**恰好 3 个互不重复、切入维度不同的可选解决方法**供家长/老师选择执行。\n\n"
        "【输出格式铁律】\n"
        "只输出一个合法 JSON 对象（不要用 Markdown 代码块以外的多余解释），字段严格如下：\n"
        "{\n"
        '  "cognitive_gap_type": "concept_confusion | condition_omission | method_misuse | reasoning_break | calculation_slip",\n'
        '  "root_cause_summary": "100~220字，直指知识漏洞或思维误区的真正原因",\n'
        '  "evidence_from_dialogue": "60~150字，结合引导对话或错误作答中的具体表现给出证据",\n'
        '  "solutions": [\n'
        "    {\n"
        '      "option_id": "opt_1",\n'
        '      "title": "方案一简短标题（如：前置概念辨析微练）",\n'
        '      "approach_focus": "侧重维度（如：概念纠偏）",\n'
        '      "rationale": "为什么这个方案针对该错因有效",\n'
        '      "action_steps": ["具体可执行动作1", "具体可执行动作2", "具体可执行动作3"]\n'
        "    },\n"
        '    {"option_id": "opt_2", "...": "..."},\n'
        '    {"option_id": "opt_3", "...": "..."}\n'
        "  ]\n"
        "}\n"
        "要求：\n"
        "1. solutions 数组必须严格包含 3 个元素，且分别从不同维度切入（例如：概念本质纠偏、审题与条件提取习惯、同类变式巩固）。\n"
        "2. 每个方案的 action_steps 包含 2~3 条学生和家长可直接落地的具体动作。\n\n"
        f"学科：{subject}\n"
        f"关联知识点：{kp_line}\n"
        f"题干：{stem}\n"
        f"{choice_lines}"
        f"参考答案：{correct_answer}\n"
        f"学生作答：{student_answer}\n"
        f"{dialogue_block}\n"
    )


def parse_error_root_cause_json(raw_text: str) -> dict[str, Any]:
    """解析并严格校验 AI 返回的错因诊断 JSON（必须包含真正错因与 3 个完整可选对策）。"""
    text = (raw_text or "").strip()
    if not text:
        raise AiTutorUnavailableError("AI 错因分析返回为空")

    # 允许模型外层包裹 ```json ... ``` 代码块，提取最外层 JSON 对象
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    elif not text.startswith("{"):
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            text = text[brace_start : brace_end + 1]

    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise AiTutorUnavailableError("AI 错因分析返回的 JSON 格式无效") from exc

    if not isinstance(parsed, dict):
        raise AiTutorUnavailableError("AI 错因分析返回结构必须为 JSON 对象")

    root_cause = str(parsed.get("root_cause_summary") or "").strip()
    evidence = str(parsed.get("evidence_from_dialogue") or "").strip()
    gap_type = str(parsed.get("cognitive_gap_type") or "").strip()
    if gap_type not in ALLOWED_COGNITIVE_GAP_TYPES:
        gap_type = "reasoning_break"

    raw_solutions = parsed.get("solutions")
    if not root_cause or not evidence or not isinstance(raw_solutions, list) or len(raw_solutions) != 3:
        raise AiTutorUnavailableError("AI 错因分析未返回完整的错因摘要与 3 个可选解决方法")

    normalized_solutions: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_solutions):
        if not isinstance(item, dict):
            raise AiTutorUnavailableError("AI 错因分析方案条目格式错误")
        title = str(item.get("title") or "").strip()
        focus = str(item.get("approach_focus") or "").strip()
        rationale = str(item.get("rationale") or "").strip()
        raw_steps = item.get("action_steps")
        steps = [str(s).strip() for s in raw_steps if str(s).strip()] if isinstance(raw_steps, list) else []
        if not title or not focus or not rationale or not steps:
            raise AiTutorUnavailableError("AI 错因分析方案缺少标题、切入角度或可执行步骤")
        normalized_solutions.append(
            {
                "option_id": f"opt_{idx + 1}",
                "title": title,
                "approach_focus": focus,
                "rationale": rationale,
                "action_steps": steps[:4],
            }
        )

    return {
        "root_cause_summary": root_cause,
        "cognitive_gap_type": gap_type,
        "evidence_from_dialogue": evidence,
        "solutions": normalized_solutions,
    }


def request_error_root_cause_analysis(
    *,
    subject: str,
    stem: str,
    choices: list[str] | None,
    correct_answer: str,
    student_answer: str,
    knowledge_titles: list[str],
    dialogue_turns: list[dict[str, str]],
) -> tuple[dict[str, Any], str]:
    """调用 LLM 分析学生错题真正原因并生成 3 个可选解决方法。"""
    prompt = build_error_root_cause_prompt(
        subject=subject,
        stem=stem,
        choices=choices,
        correct_answer=correct_answer,
        student_answer=student_answer,
        knowledge_titles=knowledge_titles,
        dialogue_turns=dialogue_turns,
    )
    raw_reply, model_used = _post_chat_completion(
        [
            {"role": "system", "content": "你是一位严谨的初中中考学情诊断与教研专家，只输出严格符合要求的结构化 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1100,
        error_label="AI 错因诊断",
        response_format={"type": "json_object"},
        min_timeout_seconds=45.0,
    )
    parsed = parse_error_root_cause_json(raw_reply)
    return parsed, model_used


_SCHOOL_COACH_ALLOWED_CATEGORIES = {"concept", "calculation", "reading", "method", "norm", "other"}
_SCHOOL_COACH_LEAK_PATTERNS = (
    r"(?:正确|最终|标准|参考)答案(?:应该)?(?:就是|是|为|选)\s*[:：]?\s*[^\s，。；！？]{1,30}",
    r"(?:所以|因此|故|应该|应当)选(?:择|项)?\s*[:：]?\s*[A-Da-d](?![A-Za-z])",
    r"(?:完整解答|解题过程|标准解析)\s*[:：]",
)
_SCHOOL_COACH_SCENE_LABELS = {
    "had_idea": "一看就有思路",
    "stuck_midway": "有思路但中途卡住",
    "no_idea": "完全没头绪",
    "no_time": "时间不够没做完",
}


def sanitize_reflection_coach_reply(
    reply: str,
    *,
    topic: str,
    has_stem: bool,
) -> tuple[str, bool]:
    """校考「书童陪你想」防泄题守卫：拦截直接报答案或甩标准解析，改为温和苏格拉底反问。"""
    cleaned = (reply or "").strip()
    kp = (topic or "").strip() or "本题考点"
    if not cleaned:
        if has_stem:
            return (
                f"我们慢慢来，先围绕「{kp}」看看题目里最关键的已知条件是什么，你当时第一步是怎么想的？",
                False,
            )
        return (
            f"我现在暂时看不到原卷文字，你能先用一句话告诉我这道关于「{kp}」的题问什么、你当时第一步是怎么想的吗？",
            False,
        )

    for pat in _SCHOOL_COACH_LEAK_PATTERNS:
        if re.search(pat, cleaned, flags=re.IGNORECASE):
            if has_stem:
                fallback = (
                    f"先不急着看最终结论哦。回到「{kp}」，你能说说题目里哪一个条件在你的步骤里没用上，"
                    "或者哪一步最容易算岔吗？"
                )
            else:
                fallback = (
                    f"先不急着看结论哦。围绕「{kp}」，你回想一下自己当时写到哪一步开始觉得不确定了？"
                )
            return fallback, True
    return cleaned, False


def build_school_reflection_coach_prompt(
    *,
    subject: str,
    topic: str,
    question_label: str,
    earned_points: float,
    max_points: float,
    stem_text: str | None,
    student_answer_text: str | None,
    scene_hint: str | None = None,
) -> str:
    """构建校考复盘「书童陪你想」三阶段微支架提示词（绝不泄答、无题干绝不编造）。"""
    kp = (topic or "").strip() or "本题考点"
    scene_cn = _SCHOOL_COACH_SCENE_LABELS.get(str(scene_hint or "").strip(), "")
    scene_line = f"学生自述考场状态：{scene_cn}\n" if scene_cn else ""
    if stem_text and stem_text.strip():
        stem_block = f"已确认原题题干：{stem_text.strip()}\n"
        honest_rule = "请结合上方已确认原题题干进行针对性提问。"
    else:
        stem_block = "已确认原题题干：暂无（系统尚未录入原卷文字）。\n"
        honest_rule = (
            "【诚实铁律】当前系统没有原卷题干文字，你绝不可以猜测或编造任何题目条件、数值或图形；"
            "开场必须先温和请学生用一句话描述这题问什么、以及当时第一步是怎么想的。"
        )
    ans_line = (
        f"学生考试时的作答：{student_answer_text.strip()}\n"
        if student_answer_text and student_answer_text.strip()
        else "学生考试时的作答：暂未录入\n"
    )
    partial_hint = (
        f"学生本题拿到了一部分步骤分（{earned_points:g}/{max_points:g} 分），请先简短肯定他已经做对的部分。"
        if earned_points > 0
        else f"学生本题失分（{earned_points:g}/{max_points:g} 分），请先温和接住情绪，避免评判和说教。"
    )
    return (
        "你是初中生的学习伙伴「我的书童」，正在「校考复盘」里一对一陪学生复盘一道校考失分题。\n"
        "目标不是把答案讲给学生听，而是用 2~4 轮简短对话陪学生自己想明白错在哪、以及下次怎么防。\n\n"
        "【核心规则】\n"
        "1. 严禁直接说出最终答案、正确选项字母或完整解题过程；哪怕学生索要答案也不要直接给。\n"
        "2. 每次回复控制在 120 字以内，每次**只问 1 个具体、容易回答的小问题**，不要一次抛多个问题。\n"
        "3. 对话按三个小阶段自然推进：① 共情并还原考场思路 → ② 帮学生指认具体卡在哪一步/漏了哪个条件 → "
        "③ 引导学生用「如果再看到…我就先…」定一个下次能直接用上的小动作。聊清楚后鼓励他点击「整理成提醒卡草稿」。\n"
        f"4. {partial_hint}\n"
        f"5. {honest_rule}\n\n"
        f"学科：{subject}｜题号：{question_label}｜考点：{kp}\n"
        f"{scene_line}"
        f"{stem_block}"
        f"{ans_line}"
    )


def request_school_reflection_coach_reply(
    *,
    system_prompt: str,
    history_turns: list[dict[str, str]],
    topic: str,
    has_stem: bool,
) -> tuple[str, bool, str]:
    """生成「书童陪你想」开场或追问回复，并经过服务端防泄题守卫净化。"""
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for item in history_turns:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    raw_reply, model_used = _post_chat_completion(
        messages,
        temperature=0.45,
        max_tokens=280,
        error_label="校考书童对话",
    )
    safe_reply, sanitized = sanitize_reflection_coach_reply(
        raw_reply,
        topic=topic,
        has_stem=has_stem,
    )
    return safe_reply, sanitized, model_used


def parse_school_reflection_summary_json(raw_text: str) -> dict[str, Any]:
    """容错解析书童整理的复盘草稿 JSON，确保错因在合法枚举内、字数受控。"""
    text = (raw_text or "").strip()
    if not text:
        raise AiTutorUnavailableError("整理提醒卡草稿返回为空")

    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    elif not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]

    try:
        parsed = json.loads(text)
    except ValueError:
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
        try:
            parsed = json.loads(repaired)
        except ValueError as exc:
            raise AiTutorUnavailableError("整理提醒卡草稿返回的 JSON 格式无效") from exc

    if not isinstance(parsed, dict):
        raise AiTutorUnavailableError("整理提醒卡草稿必须返回 JSON 对象")

    raw_cat = str(parsed.get("error_category") or "").strip()
    error_category = raw_cat if raw_cat in _SCHOOL_COACH_ALLOWED_CATEGORIES else None
    stuck_point = str(parsed.get("stuck_point") or "").strip()[:280]
    fix_strategy = str(parsed.get("fix_strategy") or "").strip()[:280]
    ready = bool(stuck_point and fix_strategy)
    return {
        "error_category": error_category,
        "stuck_point": stuck_point,
        "fix_strategy": fix_strategy,
        "ready": ready,
    }


def request_school_reflection_summary(
    *,
    subject: str,
    topic: str,
    question_label: str,
    dialogue_turns: list[dict[str, str]],
) -> tuple[dict[str, Any], str]:
    """基于学生真实对话发言忠实整理复盘草稿（绝不替学生凭空编造未说过的内容）。"""
    formatted_turns = [
        f"{idx + 1}. [{'学生' if t.get('role') == 'user' else '书童'}]: {str(t.get('content') or '').strip()}"
        for idx, t in enumerate(dialogue_turns)
        if str(t.get("content") or "").strip()
    ]
    dialogue_text = "\n".join(formatted_turns)
    prompt = (
        f"请根据以下学生与书童关于【{subject} · {question_label}（考点：{topic}）】的复盘对话，"
        "用第一人称（“我”）忠实整理出一份校考复盘草稿，方便学生修改后保存为自己的提醒卡。\n"
        "【硬性要求】\n"
        "1. 只输出严格 JSON 对象，字段如下：\n"
        '   {"error_category": "concept|calculation|reading|method|norm|other|null", '
        '"stuck_point": "学生自己说出的具体卡点或错因（15~120字；若学生还没说清则留空字符串）", '
        '"fix_strategy": "学生自己说出的下次提醒动作，建议用如果…我就先…句式（15~120字；若学生还没说到下次做法则留空字符串）"}\n'
        "2. 只能忠实提炼学生在对话中真实表达过的内容，绝不凭空编造学生没提到的解法或步骤，也不要给出标准答案。\n\n"
        f"完整对话：\n{dialogue_text}\n"
    )
    raw_reply, model_used = _post_chat_completion(
        [
            {"role": "system", "content": "你是初中学习复盘整理助手，只输出严格 JSON 对象，忠实归纳学生自己的表达。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=500,
        error_label="整理提醒卡草稿",
        response_format={"type": "json_object"},
        min_timeout_seconds=30.0,
    )
    return parse_school_reflection_summary_json(raw_reply), model_used

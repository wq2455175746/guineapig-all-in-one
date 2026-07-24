"""记忆归纳服务 — 使用 LLM 将对话归纳为结构化记忆"""

import os
import json
import httpx
from openai import OpenAI

from app.config import settings
from app.core.log import logger
from app.schemas.memory_models import MemorySummarizeRequest

MEMORY_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "asset",
    "MEMORY_template.md",
)

MEMORY_TYPE_DESCRIPTIONS = """
记忆类型说明（请选择最合适的一种）：
- daily_summary：对用户某一天（或某一段连续对话）的整体概括，记录当天聊了什么、发生了什么
- topic_summary：按话题/项目/领域聚合的记忆，跨时间维度归纳用户在某个主题下的所有讨论
- key_fact：用户表达的确定性信息，包括身份、职业、技能、关系、偏好设置等静态或半静态属性
- preference：用户明确表达的喜好、风格要求、操作习惯，通常以"I prefer..."、"下次请..."、"我不喜欢..."等形式出现
"""

SYSTEM_PROMPT = """你是一个专业的记忆归纳助手。请根据用户的对话内容，结合已有的历史记忆，生成更新后的 4 种结构化记忆：

1. daily_summary：对用户近期整体的概括（融合历史 + 新对话）
2. topic_summary：按话题/项目/领域聚合的记忆
3. key_fact：用户表达的确定性信息（身份、职业、技能等）
4. preference：用户明确表达的喜好、风格要求、操作习惯

### 历史记忆融合规则：
- 参考上方"已有记忆参考"中的内容，将其与今天的新对话融合，生成更新后的记忆
- 已有记忆中的有效信息应继承到新记忆中，不要重复创建相同内容
- 如果新对话内容与已有记忆冲突，以新内容为准
- **越早的记忆置信度越低**，应以近期对话为主进行融合
- 生成结果是**一轮完整的新记忆**（不是增量补充），应涵盖本轮时间窗口中的所有重要信息

请严格按照以下 JSON 数组格式输出，每条记忆对应一个对象，全部 4 种类型都要生成：
[
  {
    "name": "简短的记忆名称（15字以内）",
    "mem_type": "daily_summary",
    "mem": "完整的记忆内容（使用 Markdown 格式，参考记忆模板）",
    "confidence_score": 1-10之间的整数
  },
  {
    "name": "...",
    "mem_type": "topic_summary",
    "mem": "...",
    "confidence_score": ...
  },
  {
    "name": "...",
    "mem_type": "key_fact",
    "mem": "...",
    "confidence_score": ...
  },
  {
    "name": "...",
    "mem_type": "preference",
    "mem": "...",
    "confidence_score": ...
  }
]

如果没有某类记忆的合适内容，可以填入空字符串或相关内容，但必须包含全部 4 种类型。
返回的 mem 内容要使用 Markdown 格式组织，包含引用对话原文。
只输出 JSON 数组，不要包含其他说明文字。"""


def _load_memory_template() -> str:
    """加载记忆模板文件"""
    try:
        with open(MEMORY_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"记忆模板文件不存在: {MEMORY_TEMPLATE_PATH}")
        return ""


def _build_conversation_text(req: MemorySummarizeRequest) -> str:
    """将对话数据组织成 LLM 可读的文本"""
    lines = []
    lines.append(f"时间范围：{req.time_range_start} ~ {req.time_range_end}")
    lines.append("")
    lines.append("=== 对话列表 ===")
    for conv in req.conversations:
        lines.append(f"对话 #{conv.id}: {conv.title} ({conv.created_at})")
    lines.append("")
    lines.append("=== 消息内容 ===")
    for msg in req.messages:
        role_label = (
            "用户"
            if msg.role == "user"
            else ("助手" if msg.role == "assistant" else msg.role)
        )
        lines.append(f"[{role_label}] {msg.content}")
    return "\n".join(lines)


def _build_existing_memories_text(req: MemorySummarizeRequest) -> str:
    """将已有记忆组织成 LLM 可读的文本（按时间倒序，越早权重越低）"""
    if not req.existing_memories:
        return ""

    lines = []
    lines.append("=== 已有记忆参考（按时间倒序，越早置信度越低） ===")
    for m in req.existing_memories:
        date_str = m.created_at[:10] if m.created_at else "未知"
        start_str = m.time_range_start_at[:10] if m.time_range_start_at else ""
        end_str = m.time_range_end_at[:10] if m.time_range_end_at else ""
        time_range = f" ({start_str} ~ {end_str})" if start_str and end_str else ""
        lines.append(
            f"\n--- [{date_str}] {m.mem_type}: {m.name} (v{m.version}){time_range} ---"
        )
        lines.append(m.mem)
    return "\n".join(lines)


def _strip_markdown_code_block(text: str) -> str:
    """去掉 markdown 代码块包裹"""
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return text


def _callback_backend(url: str, payload: dict) -> None:
    """向 backend 发送回调请求"""
    logger.info(
        f"[MemorySummarize] 回调: type={payload.get('mem_type')}, memory_id={payload.get('id')}"
    )
    resp = httpx.post(url, json=payload, timeout=30)
    resp.raise_for_status()


def process_memory_summarize(req: MemorySummarizeRequest):
    """处理记忆归纳请求"""
    logger.info(
        f"[MemorySummarize] 开始处理: memory_id={req.memory_id}, user_id={req.user_id}"
    )

    # 1. 加载模板 + 构建 prompt
    template = _load_memory_template()
    conversation_text = _build_conversation_text(req)
    existing_memories_text = _build_existing_memories_text(req)

    if existing_memories_text:
        user_prompt = f"""{MEMORY_TYPE_DESCRIPTIONS}

参考格式（记忆模板）：
{template}

{existing_memories_text}

今日对话内容：
{conversation_text}

请结合上述"已有记忆参考"和今日对话内容，生成融合更新后的 4 种结构化记忆。已有记忆中的有效信息应继承到新记忆中。"""
    else:
        user_prompt = f"""{MEMORY_TYPE_DESCRIPTIONS}

参考格式（记忆模板）：
{template}

对话内容：
{conversation_text}

请根据以上对话内容，生成 4 种类型的结构化记忆（daily_summary, topic_summary, key_fact, preference）。"""

    # 2. 调用 LLM
    try:
        client = OpenAI(
            api_key=req.model_info.api_key,
            base_url=req.model_info.base_url,
        )

        logger.info(f"[MemorySummarize] 调用 LLM: model={req.model_info.model_name}")
        completion = client.chat.completions.create(
            model=req.model_info.model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        result_text = completion.choices[0].message.content.strip()
        logger.info(f"[MemorySummarize] LLM 返回: {result_text[:200]}...")
    except Exception as e:
        logger.error(f"[MemorySummarize] LLM 调用失败: {e}")
        raise

    # 3. 解析 JSON 结果（兼容数组和单个对象两种格式）
    result_text = _strip_markdown_code_block(result_text)
    try:
        parsed = json.loads(result_text.strip())
    except json.JSONDecodeError as e:
        logger.error(f"[MemorySummarize] JSON 解析失败: {e}, raw={result_text}")
        raise ValueError(f"LLM 返回结果解析失败: {e}")

    if isinstance(parsed, dict):
        parsed_list = [parsed]
    elif isinstance(parsed, list):
        parsed_list = parsed
    else:
        raise ValueError(f"LLM 返回格式错误，期望对象或数组: {type(parsed)}")

    conv_ids_str = json.dumps([c.id for c in req.conversations])
    source_msg_count = len(req.messages)
    backend_url = f"{settings.BACKEND_BASE_URL}/inner/api/v1/memory/update-content"

    # 4. 逐一回调 backend 更新记忆内容
    results = []
    for entry in parsed_list:
        mem_type = entry.get("mem_type", "")
        memory_id = req.memory_ids.get(mem_type, req.memory_id)
        name = entry.get("name", f"记忆归纳 {req.time_range_start[:10]}")
        mem_content = entry.get("mem", "")
        confidence_score = entry.get("confidence_score", 5)

        callback_payload = {
            "id": str(memory_id),
            "name": name,
            "mem": mem_content,
            "mem_type": mem_type,
            "conversation_ids": conv_ids_str,
            "source_msg_count": source_msg_count,
            "time_range_start_at": req.time_range_start,
            "time_range_end_at": req.time_range_end,
        }

        try:
            _callback_backend(backend_url, callback_payload)
            logger.info(f"[MemorySummarize] {mem_type} 回调成功: memory_id={memory_id}")
            results.append({"memory_id": memory_id, "name": name, "mem_type": mem_type})
        except Exception as e:
            logger.error(
                f"[MemorySummarize] {mem_type} 回调失败: memory_id={memory_id}, error={e}"
            )
            raise

    return results

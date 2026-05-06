import json
import os
import time
import uuid
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from collections import OrderedDict

from dotenv import load_dotenv
from openai import OpenAI
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from src.protocol import AgentResponse, UserMessage, AssistantMessage, ToolMessage, ToolCallData,Message
#from tools.export_docs import export_tools_json
from tools.export_docs import export_tools_json
from src.rag import init_vectorstore  # 你的向量库初始化函数，建议移到独立模块

# 配置
MAX_RETRIES = 3
THINKING_MODE = True
MODEL_NAME = "qwen3.5-flash"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_RULES_PATH = str(PROJECT_ROOT / "knowledge" / "project_rules.md")

load_dotenv()
qwen_api_key = os.getenv("QWEN_API_KEY")
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

client = OpenAI(
    api_key = qwen_api_key,
    base_url = base_url
)

# 初始化全局对象（服务启动时加载）
retri = None
tools_schema = None

# 指令级模板缓存（缓存工具结构，不缓存具体参数）
TEMPLATE_CACHE_MAX_ENTRIES = 500
instruction_template_cache: OrderedDict[str, List[str]] = OrderedDict()
template_cache_hit_total = 0
template_cache_miss_total = 0
template_cache_hit_latency_ms_sum = 0.0
template_cache_miss_latency_ms_sum = 0.0


def _normalize_instruction_signature(text: str) -> str:
    """归一化用户指令，用于模板级缓存命中。"""
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"-?\d+(?:\.\d+)?", "<num>", normalized)
    normalized = re.sub(r"#[0-9a-f]{3,8}", "<color>", normalized)
    normalized = re.sub(r"\([^)]*\)", "(<args>)", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def get_template_cache_metrics() -> Dict[str, Any]:
    total = template_cache_hit_total + template_cache_miss_total
    hit_rate = (template_cache_hit_total / total) if total else 0.0
    hit_avg_latency = (template_cache_hit_latency_ms_sum / template_cache_hit_total) if template_cache_hit_total else 0.0
    miss_avg_latency = (template_cache_miss_latency_ms_sum / template_cache_miss_total) if template_cache_miss_total else 0.0
    return {
        "template_cache_hit_total": template_cache_hit_total,
        "template_cache_miss_total": template_cache_miss_total,
        "template_cache_hit_rate": round(hit_rate, 4),
        "template_cache_entries": len(instruction_template_cache),
        "template_cache_max_entries": TEMPLATE_CACHE_MAX_ENTRIES,
        "template_cache_hit_avg_latency_ms": round(hit_avg_latency, 2),
        "template_cache_miss_avg_latency_ms": round(miss_avg_latency, 2),
    }

def load_rag_and_tools():
    global retri, tools_schema
    retri = init_vectorstore(PROJECT_RULES_PATH)
    tools_schema = export_tools_json()

def convert_to_api_messages(conversation: list[Message]) -> list[dict]:
    api_messages = []
    for idx,msg in enumerate(conversation):
        if not isinstance(msg, dict):
            # 如果传入的是 Pydantic 模型，转成字典（备用）
            msg = msg.model_dump(exclude_none=True)
        new_msg = msg.copy()
        if new_msg.get("role") == "assistant" and "tool_calls" in new_msg:
            api_tool_calls = []
            for tc in new_msg["tool_calls"]:
                name = tc.get("name")
                args = tc.get("arguments")
                call_id = tc.get("id", f"call_{uuid.uuid4().hex[:8]}")
                # 如果 arguments 是字典，序列化为 JSON 字符串
                if isinstance(args, dict):
                    args_str = json.dumps(args, ensure_ascii=False)
                else:
                    args_str = args
                api_tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": args_str
                    }
                })
            new_msg["tool_calls"] = api_tool_calls
        elif msg.get("role") == "tool":
            tool_msg = {
                "role": "tool",
                "tool_call_id": msg["tool_call_id"],
                "content": msg["content"]
            }
            api_messages.append(tool_msg)
            continue
        api_messages.append(new_msg)
    return api_messages

def plan_next_step(history_messages: List[Dict], step_count: int = 0) -> AgentResponse:
    """
    根据完整历史消息（包含用户输入、助手回复、工具结果），返回下一步规划结果。
    """
    # 如果历史最后一条不是用户消息，说明是工具结果后继续，直接使用历史
    if history_messages and history_messages[-1].get("role") != "user":
        current_messages = history_messages
    else:
        # 否则提取最后一条用户消息作为当前输入
        user_input = history_messages[-1].get("content", "")
        current_messages = history_messages[:-1] + [{"role": "user", "content": user_input}]

    # 调用 LLM 获取响应
    response = call_llm(current_messages, retri, tools_schema)
    return response

def call_llm(messages: list, retri, tools_schema, max_retries=MAX_RETRIES) -> AgentResponse:
    global template_cache_hit_total, template_cache_miss_total
    global template_cache_hit_latency_ms_sum, template_cache_miss_latency_ms_sum
    started_at = time.perf_counter()

    # 历史消息
    user_content = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
    signature = _normalize_instruction_signature(user_content)
    cached_tool_sequence = instruction_template_cache.get(signature)
    if cached_tool_sequence:
        template_cache_hit_total += 1
        # LRU: 命中后刷新为最近使用
        instruction_template_cache.move_to_end(signature)
    else:
        template_cache_miss_total += 1

    relevant_rules_docs = retri.invoke(user_content)

    project_rules_context = "\n\n".join([doc.page_content for doc in relevant_rules_docs])
    # print(f"📏 RAG内容长度: {len(project_rules_context)} 字符")

    system_content = f"""
        你是一个 Unity 编辑器助手。
        你的任务是分析用户意图，并严格根据【可用工具列表】选择合适的工具进行调用。

        # 1. 可用工具列表
        {json.dumps(tools_schema, indent=2, ensure_ascii=False)}

        # 2. 开发规范
        请严格遵循以下规范来填充参数：
        {project_rules_context}

        # 3. 输出格式
        请严格按照 JSON 格式输出，包含 `thoughts` 和 `tool_calls` 字段。

        示例(单个或多个工具调用)：
        {{
          "thoughts": "用户需要创建方块",
          "tool_calls": [
            {{
              "name": "create_object",
              "arguments": {{
                "type": "Cube",
                "object_name": "Gen_Cube",
                "position": [0,0,0],
                "localRotation": [0,0,0],
                "localScale": [1,1,1]
              }}
            }},
          ]
        }}

        示例（任务完成）：
        {{
          "thoughts": "所有步骤已成功执行，无需进一步操作。",
          "content": "已为您创建方块。"
        }}

        优化建议:
        当需要创建多个相同配置的物体时（例如多个带脚本的立方体），可以采用以下高效步骤：
        1. 创建一个基础物体，并为其挂载所需的脚本，设置好属性。
        2. 使用 `duplicate_object` 工具复制出其余物体，并调整它们的位置。

        注意：
        - 分批策略：若工具超过5个，请分批输出（每批≤5），并在thoughts中说明后续。
        - 依赖关系：通过对话历史传递物体名称等中间结果。
        - 参数完整：每个工具调用必须包含所有必要参数。
        - 避免重复：已成功执行的步骤不要重复调用。
        - 错误处理：遇到“Unity正在编译”类错误，下次重发指令即可。
        - 任务完成：所有步骤成功后，直接输出content（不再调用工具）。
        """

    if cached_tool_sequence:
        system_content += f"""

        # 指令模板缓存提示（仅作结构参考）
        本次命中了历史工具结构缓存，可优先参考以下工具序列：
        {json.dumps(cached_tool_sequence, ensure_ascii=False)}
        注意：这是参考信息，参数仍需根据当前输入重新生成。
        """

    base_messages = messages  # 原始的对话历史（不含反馈）
    feedbacks = []  # 存储错误反馈

    for attempt in range(max_retries + 1):

        # 构建完整消息列表
        converted_history = convert_to_api_messages(base_messages)
        full_messages = [{"role": "system", "content": system_content}] + converted_history + feedbacks

        # llm_log日志 记录请求
        # timestamp = datetime.now().isoformat()
        # with open("llm_log.txt", "a", encoding="utf-8") as f:
        #     f.write(f"\n--- {timestamp} 请求 ---\n")
        #     json.dump(full_messages, f, indent=2, ensure_ascii=False)
        #     f.write("\n")

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                extra_body={"enable_thinking": THINKING_MODE},
                messages=full_messages,
                stream=False,
                response_format={"type": "json_object"}
            )
            json_str = response.choices[0].message.content

            # llm_log日志 记录响应
            # with open("llm_log.txt", "a", encoding="utf-8") as f:
            #     f.write(f"--- {timestamp} 响应 ---\n")
            #     f.write(json_str + "\n")

            parsed_response = AgentResponse.model_validate_json(json_str)
            if parsed_response.tool_calls:
                instruction_template_cache[signature] = [tc.name for tc in parsed_response.tool_calls]
                instruction_template_cache.move_to_end(signature)
                while len(instruction_template_cache) > TEMPLATE_CACHE_MAX_ENTRIES:
                    instruction_template_cache.popitem(last=False)
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            if cached_tool_sequence:
                template_cache_hit_latency_ms_sum += elapsed_ms
            else:
                template_cache_miss_latency_ms_sum += elapsed_ms
            return parsed_response

        except Exception as e:
            print(f"⚠️ 第{attempt + 1}次调用失败: {e}")
            if attempt < max_retries:
                if attempt == max_retries - 1:
                    feedback_msg = {
                        "role": "user",
                        "content": f"你上次的输出解析失败：{e}。请确保输出是有效的 JSON 对象，包含 thoughts 和 tool_calls（或 content）字段。"
                    }
                    feedbacks.append(feedback_msg)
                    print("🔄 已添加错误反馈，等待1秒后重试...")
                time.sleep(1)
            else:
                print("❌ 多次重试失败，返回错误响应")
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                if cached_tool_sequence:
                    template_cache_hit_latency_ms_sum += elapsed_ms
                else:
                    template_cache_miss_latency_ms_sum += elapsed_ms
                return AgentResponse(
                    thoughts="LLM连续多次响应异常。",
                    content="指令生成失败，请稍后重试或简化请求。"
                )

    # 理论上不会走到这里，仅用于静态检查与兜底保护。
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    if cached_tool_sequence:
        template_cache_hit_latency_ms_sum += elapsed_ms
    else:
        template_cache_miss_latency_ms_sum += elapsed_ms
    return AgentResponse(
        thoughts="未命中有效返回路径。",
        content="指令生成失败，请稍后重试。"
    )
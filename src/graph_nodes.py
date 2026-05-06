from __future__ import annotations
import time
import json
from typing import Any, Callable, Dict, List, Optional

from src.graph_state import GraphState
from src.protocol import AgentResponse, ToolCall, validate_tool_calls


def _extract_latest_user_content(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return ""
    last_message = messages[-1]
    if last_message.get("role") == "user":
        return last_message.get("content", "")
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _build_system_prompt(
    project_rules_context: str,
    cached_tool_sequence: Optional[List[str]] = None,
) -> str:
    system_content = f"""
        你是一个 Unity 编辑器助手。
        目标:根据用户意图选择必要工具，或直接返回自然语言回复。

        # 规则：
        - 只在确实需要执行 Unity 操作时调用工具
        - 无法确定时，不要乱猜工具，优先返回 content
        - 参数必须符合项目规范
        - 已成功的步骤不要重复调用


        # 项目规则
        请严格遵循以下规范来填充参数：
        {project_rules_context}

        # 输出：
        - 需要工具时使用原生 tool calling
        - 不需要工具时直接返回 content
        """

    if cached_tool_sequence:
        system_content += f"""

        # 指令模板缓存提示（仅作结构参考）
        本次命中了历史工具结构缓存，可优先参考以下工具序列：
        {json.dumps(cached_tool_sequence, ensure_ascii=False)}
        注意：这是参考信息，参数仍需根据当前输入重新生成。
        """

    return system_content


def _convert_to_api_messages(conversation: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    api_messages: List[Dict[str, Any]] = []
    for message in conversation:
        current = message.copy()
        if current.get("role") == "assistant" and "tool_calls" in current:
            api_tool_calls = []
            for tool_call in current["tool_calls"]:
                name = tool_call.get("name")
                arguments = tool_call.get("arguments")
                call_id = tool_call.get("id", f"call_{id(tool_call)}")
                arguments_text = json.dumps(arguments, ensure_ascii=False) if isinstance(arguments, dict) else arguments
                api_tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": arguments_text,
                        },
                    }
                )
            current["tool_calls"] = api_tool_calls
        elif current.get("role") == "tool":
            api_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": current.get("tool_call_id"),
                    "content": current.get("content", ""),
                }
            )
            continue
        api_messages.append(current)
    return api_messages


def retrieve_rules_node(state: GraphState) -> Dict[str, Any]:
    started_at = time.perf_counter()

    metrics = state.setdefault("metrics", {})
    messages = state.get("messages", [])
    retriever = state.get("retriever")
    if retriever is None:
        return {"error": "Missing retriever for retrieve_rules_node."}

    user_content = _extract_latest_user_content(messages)
    retrieved_docs = retriever.invoke(user_content)

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    metrics["retrieve_latency_ms_sum"] = metrics.get("retrieve_latency_ms_sum", 0.0) + elapsed_ms
    metrics["retrieved_doc_total"] = metrics.get("retrieved_doc_total", 0) + len(retrieved_docs)

    project_rules_context = "\n\n".join([doc.page_content for doc in retrieved_docs])
    return {
        "project_rules_context": project_rules_context,
        "error": "",
        "metrics": metrics
    }


def plan_node(state: GraphState) -> Dict[str, Any]:

    result:Dict[str, Any] = {}
    started_at = time.perf_counter()
    llm_started_at = None

    messages = state.get("messages", [])
    tools = state.get("tools")
    plan_callable = state.get("plan_callable")
    metrics = state.setdefault("metrics", {})
    try:
        if not callable(plan_callable):
            raise TypeError("Missing plan_callable for plan_node.")

        user_content = _extract_latest_user_content(messages)
        signature = state.get("instruction_signature") or user_content
        cached_tool_sequence = state.get("cached_tool_sequence")
        project_rules_context = state.get("project_rules_context", "")
        system_content = _build_system_prompt(project_rules_context, cached_tool_sequence)
        converted_history = _convert_to_api_messages(messages)
        full_messages = [{"role": "system", "content": system_content}] + converted_history
        available_tools = tools.get("tools", []) if isinstance(tools, dict) else []

        llm_started_at = time.perf_counter()
        response = plan_callable(full_messages, available_tools)

        if response is None:
            raise TypeError("plan_callable returned None.")
        if not isinstance(response, AgentResponse):
            raise TypeError(f"plan_callable returned invalid type: {type(response)}. Expected AgentResponse.")

        result = {
            "tool_calls": [tool_call.model_dump(exclude_none=True) for tool_call in response.tool_calls],
            "final_content": response.content or "",
            "thoughts": response.thoughts or "",
            "instruction_signature": signature,
            "error": "",
            "metrics": metrics,
            "plan_retryable": False,
        }
    except Exception as e:
        can_retry =  state.get("llm_retry_count", 0) < state.get("llm_retry_limit", 0)
        result = {
            "error": str(e),
            "metrics": metrics,
            "last_error": str(e),
            "llm_retry_count": state.get("llm_retry_count", 0) + 1,
            "plan_retryable":can_retry,
            "feedback_messages": state.get("feedback_messages", []) + [{"role": "system", "content": f"规划错误: {str(e)}. 请根据错误信息调整指令或工具调用并重试."}]
            }
    finally:
        if llm_started_at:
            llm_elapsed_ms = int((time.perf_counter() - llm_started_at) * 1000)
            metrics["llm_latency_ms_sum"] = metrics.get("llm_latency_ms_sum", 0.0) + llm_elapsed_ms
            metrics["llm_call_total"] = metrics.get("llm_call_total", 0) + 1

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        metrics["plan_latency_ms_sum"] = metrics.get("plan_latency_ms_sum", 0.0) + elapsed_ms
        metrics["plan_call_total"] = metrics.get("plan_call_total", 0) + 1
    
    result["metrics"] = metrics
    return result




def validate_node(state: GraphState) -> Dict[str, Any]:

    result: Dict[str, Any] = {}
    started_at = time.perf_counter()
    metrics = state.setdefault("metrics", {})

    try:
        raw_tool_calls = state.get("tool_calls", [])
        if not raw_tool_calls:
            raise TypeError("No tool calls to validate in validate_node.")

        tool_calls = [ToolCall.model_validate(tool_call) for tool_call in raw_tool_calls]
        response = AgentResponse(
            thoughts=state.get("thoughts", ""),
            content=state.get("final_content"),
            tool_calls=tool_calls,
        )
        validated_tools = validate_tool_calls(response)

        if tool_calls and not validated_tools:
            raise TypeError("All tool calls failed validation.")

        result = {"tool_calls": validated_tools, "error": "", "metrics": metrics}

    except Exception as e:
        can_retry = state.get("validation_retry_count", 0) < state.get("validation_retry_limit", 0)
        result = {
            "error": str(e),
            "tool_calls": [],
            "metrics": metrics,
            "last_error": str(e),
            "validation_retry_count": state.get("validation_retry_count", 0) + 1,
            "validation_retryable": can_retry,
            "feedback_messages": state.get("feedback_messages", []) + [{"role": "system", "content": f"验证错误: {str(e)}. 请根据错误信息调整工具调用并重试."}] 
        }
    finally:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        metrics["validation_latency_ms_sum"] = metrics.get("validation_latency_ms_sum", 0.0) + elapsed_ms
        metrics["validation_call_total"] = metrics.get("validation_call_total", 0) + 1
    result["metrics"] = metrics
    return result


def finish_node(state: GraphState) -> Dict[str, Any]:
    metrics = state.setdefault("metrics", {})
    if state.get("error"):
        return {"error": state.get("error"), "metrics": metrics}

    if state.get("tool_calls"):
        return {
            "final_content": state.get("final_content", ""),
            "error": "",
            "metrics": metrics
        }

    return {
        "final_content": state.get("final_content", ""),
        "error": "",
        "metrics": metrics
    }

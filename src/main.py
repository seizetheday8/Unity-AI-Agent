import json
import time
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import uuid
from collections import Counter
from src.agent_planner import plan_next_step, load_rag_and_tools
from src.protocol import ToolCall, AgentResponse, PROTOCOL_VERSION, ErrorEnvelope


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_rag_and_tools()
    yield

app = FastAPI(title="Unity AI Agent API",lifespan=lifespan)


# 轻量内存指标，适合先验证埋点价值。
METRICS = {
    "execute_total": 0,
    "execute_error_total": 0,
    "execute_latency_ms_sum": 0.0,
    "tool_call_total": 0,
    "tool_name_counter": Counter(),
    "plan_latency_ms_sum": 0.0,
    "plan_call_total": 0,
    "llm_latency_ms_sum": 0.0,
    "llm_call_total": 0,
    "retrieve_latency_ms_sum": 0.0,
    "retrieved_doc_total": 0,
    "validation_latency_ms_sum": 0.0,
    "validation_call_total": 0,
}


def stringify_tool_arguments(tool_calls: List[Any]) -> List[ToolCall]:
    """递归处理工具调用，将特定字段转为 JSON 字符串"""
    new_tool_calls = []
    for tc in tool_calls:
        # 将 arguments 转为字典（如果是 Pydantic 模型）
        if hasattr(tc.arguments, 'model_dump'):
            args_dict = tc.arguments.model_dump()
        else:
            args_dict = tc.arguments
        # 处理 attach_script
        if tc.name == "attach_script" and "script_parameters" in args_dict:
            param = args_dict["script_parameters"]
            if param is not None and not isinstance(param, str):
                args_dict["script_parameters"] = json.dumps(param, ensure_ascii=False)
        # 处理 modify_script_properties
        if tc.name == "modify_script_properties" and "new_script_parameters" in args_dict and args_dict[
                "new_script_parameters"] is not None:
            param = args_dict["new_script_parameters"]
            args_dict["new_script_parameters"] = json.dumps(param, ensure_ascii=False)
            # 将整个 args_dict 转为 JSON 字符串
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        new_tool_calls.append(ToolCall(
            id=call_id,
            name=tc.name,
            arguments=args_dict
        ))
    return new_tool_calls

class ExecuteRequest(BaseModel):
    protocol_version: str = PROTOCOL_VERSION
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: Optional[str] = None
    message_type: str = "user_request"
    payload: Optional[Dict[str, Any]] = None
    history: List[Dict] = Field(default_factory=list)           # 兼容旧协议：历史消息由客户端直接传递


def _extract_history(req: ExecuteRequest) -> List[Dict]:
    if req.payload and isinstance(req.payload, dict):
        payload_history = req.payload.get("history")
        if isinstance(payload_history, list):
            return payload_history
    return req.history or []

@app.post("/execute")
async def execute(req: ExecuteRequest):
    start_time = time.perf_counter()
    METRICS["execute_total"] += 1
    try:
        history = _extract_history(req)
        session_id = req.session_id or str(uuid.uuid4())
        request_id = req.request_id or str(uuid.uuid4())
        timestamp = req.timestamp or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"

        user_input = ""
        if history and history[-1].get("role") == "user":
            user_input = history[-1].get("content", "")

        response, metrics = plan_next_step(history)
        METRICS["plan_latency_ms_sum"] += metrics.get("plan_latency_ms_sum", 0)
        METRICS["plan_call_total"] += metrics.get("plan_call_total", 0)
        METRICS["llm_latency_ms_sum"] += metrics.get("llm_latency_ms_sum", 0)
        METRICS["llm_call_total"] += metrics.get("llm_call_total", 0)
        METRICS["retrieve_latency_ms_sum"] += metrics.get("retrieve_latency_ms_sum", 0)
        METRICS["retrieved_doc_total"] += metrics.get("retrieved_doc_total", 0)
        METRICS["validation_latency_ms_sum"] += metrics.get("validation_latency_ms_sum", 0)
        METRICS["validation_call_total"] += metrics.get("validation_call_total", 0)

        print(f"[request_id={request_id}] 用户输入:{user_input}")
        # 构建返回的字典
        result = AgentResponse(
            protocol_version=req.protocol_version or PROTOCOL_VERSION,
            session_id = session_id,
            request_id = request_id,
            timestamp = timestamp,
            message_type = "planning_result" if response.tool_calls else "final_reply",
            thoughts = response.thoughts,
            content = response.content,
            tool_calls = []
        )
        if response.tool_calls:
            result.tool_calls = stringify_tool_arguments(response.tool_calls)
            METRICS["tool_call_total"] += len(response.tool_calls)
            for tc in response.tool_calls:
                METRICS["tool_name_counter"][tc.name] += 1
            result.payload = {
                "tool_call_count": len(response.tool_calls),
                "history_length": len(history),
            }
            print(f"[request_id={request_id}] 返回数据: {result}")
        else:
            result.payload = {
                "history_length": len(history),
            }
        return result
    except Exception as e:
        METRICS["execute_error_total"] += 1
        import traceback
        traceback.print_exc()   # 打印完整堆栈
        error_envelope = ErrorEnvelope(
            session_id=req.session_id or str(uuid.uuid4()),
            request_id=req.request_id or str(uuid.uuid4()),
            error_code="RUNTIME_EXECUTE_FAILED",
            error_message=str(e),
            recoverable=False,
            suggested_action="检查后端日志和 Unity 端入参是否符合协议",
            payload={"exception_type": type(e).__name__},
        )
        raise HTTPException(status_code=500, detail=error_envelope.model_dump())
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        METRICS["execute_latency_ms_sum"] += elapsed_ms

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    execute_total = METRICS["execute_total"]
    avg_latency_ms = METRICS["execute_latency_ms_sum"] / execute_total if execute_total else 0.0
    error_rate = METRICS["execute_error_total"] / execute_total if execute_total else 0.0

    return {
        "execute_total": execute_total,
        "execute_error_total": METRICS["execute_error_total"],
        "execute_error_rate": round(error_rate, 4),
        "execute_avg_latency_ms": round(avg_latency_ms, 2),
        "tool_call_total": METRICS["tool_call_total"],
        "tool_name_counter": dict(METRICS["tool_name_counter"]),
        "plan_latency_ms_sum": METRICS["plan_latency_ms_sum"],
        "plan_call_total": METRICS["plan_call_total"],
        "llm_latency_ms_sum": METRICS["llm_latency_ms_sum"],
        "llm_call_total": METRICS["llm_call_total"],
        "retrieve_latency_ms_sum": METRICS["retrieve_latency_ms_sum"],
        "retrieved_doc_total": METRICS["retrieved_doc_total"],
        "validation_latency_ms_sum": METRICS["validation_latency_ms_sum"],
        "validation_call_total": METRICS["validation_call_total"],
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
import json
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional,Any
import uuid
from agent_planner import plan_next_step, load_rag_and_tools
from src.protocol import ToolCall, AgentResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_rag_and_tools()
    yield

app = FastAPI(title="Unity AI Agent API",lifespan=lifespan)

def stringify_tool_arguments(tool_calls: List[Any]) -> List[Any]:
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
        args_str = json.dumps(args_dict, ensure_ascii=False)
        new_tool_calls.append({
            "id": call_id,
            "name": tc.name,
            "arguments": args_str
        })
    return new_tool_calls

class ExecuteRequest(BaseModel):
    session_id: Optional[str] = None
    #user_input: str
    history: List[Dict] = []           # 历史消息，由客户端维护并传递

@app.post("/execute")
async def execute(req: ExecuteRequest):
    try:
        user_input = ""
        if req.history and req.history[-1].get("role") == "user":
            user_input = req.history[-1].get("content","")

        response = plan_next_step(req.history)
        print(f"用户输入:{user_input}")
        # 构建返回的字典
        result = AgentResponse(
            session_id = response.session_id,
            thoughts = response.thoughts,
            content = response.content,
            tool_calls = None
        )
        if response.tool_calls:
            result["tool_calls"] = stringify_tool_arguments(response.tool_calls)
            print(f"返回数据: {result}")
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()   # 打印完整堆栈
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
import uuid
from typing import List, Optional, Literal, Any,Union
from pydantic import BaseModel, Field, model_validator,field_validator


# ==================== 物体操作 ====================

class CreateObjectArgs(BaseModel):
    type: Literal["Cube", "Sphere","Cylinder","Capsule","Plane","Quad"] = "Cube"
    object_name: str = "NewObject"
    position: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    localRotation: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    localScale: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])

class DeleteObjectArgs(BaseModel):
    object_name: str

class ModifyObjectArgs(BaseModel):
    object_name: str
    new_object_name: Optional[str] = None
    position: Optional[List[float]] = None
    localRotation: Optional[List[float]] = None
    localScale: Optional[List[float]] = None

class DuplicateObjectArgs(BaseModel):
    object_name: str
    new_object_name: Optional[str] = None
    position: Optional[List[float]] = None
    localRotation: Optional[List[float]] = None
    localScale: Optional[List[float]] = None

    class Config:
        extra = "forbid"

# ==================== 查询 ====================

class GetSelectedObjectArgs(BaseModel):
    pass

class GetSceneObjectsArgs(BaseModel):
    pass

# ==================== 材质 ====================

class CreateMaterialArgs(BaseModel):
    material_name: str = "NewMaterial"
    colorHex: str = "#FFFFFF"

class SetMaterialArgs(BaseModel):
    object_name: str
    material_name: str

# ==================== 脚本 ====================

class AttachScriptArgs(BaseModel):
    object_name: str
    script_name: str
    script_parameters: Optional[dict] = None

    class Config:
        extra = 'forbid'

class ModifyScriptPropertiesArgs(BaseModel):
    object_name: str
    script_name: str
    new_script_parameters: dict

    class Config:
        extra = "forbid" # 忽略 LLM 偶尔产生的多余字段，避免污染

# ==================== 预制体 ====================

class CreatePrefabArgs(BaseModel):
    object_name:str
    prefab_name: str
    path: str
    position: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    localRotation: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    localScale: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])

class EchoArgs(BaseModel):
    text: str

# ==================== 对话消息参数模型 ====================
class SystemMessage(BaseModel):
    role: Literal["system"] = "system"
    content: str

class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str

class ToolCallData(BaseModel):
    id:str
    name: str
    arguments: dict

class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCallData]] = None

    @model_validator(mode='after')
    def check_content_or_tool_calls(self):
        if self.content is None and not self.tool_calls:
            raise ValueError("Assistant message must have either content or tool_calls")
        return self

class ToolMessage(BaseModel):
    role: Literal["tool"] = "tool"
    tool_call_id: Optional[str] = None  # 可以留空或用工具名
    name: str  # 工具名
    content: str  # 工具执行结果（JSON字符串）

# 联合类型，表示任意消息
Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]

class ToolCall(BaseModel):
    """
    这是 LLM 返回的标准结构
    对应 OpenAI 的 tool_calls 格式
    """
    # 工具名称 对应action
    name: Literal[
        "create_object",
        "delete_object",
        "modify_object",
        "duplicate_object",
        "get_scene_objects",
        "get_selected_object",
        "create_material",
        "set_material",
        "attach_script",
        "modify_script_properties",
        "create_prefab",
        "echo"
    ]
    # 具体参数，这里用 Dict 接收，后续再根据 name 解析
    arguments: Union[
        CreateObjectArgs,
        DeleteObjectArgs,
        ModifyObjectArgs,
        DuplicateObjectArgs,
        GetSelectedObjectArgs,
        GetSceneObjectsArgs,
        CreateMaterialArgs,
        SetMaterialArgs,
        AttachScriptArgs,
        ModifyScriptPropertiesArgs,
        CreatePrefabArgs,
        EchoArgs,
        dict[str, Any]
    ]

    # --- 核心：自动把字典转成对应的强类型对象 ---
    @field_validator('arguments',mode='after')
    @classmethod
    def convert_arguments_to_model(cls, v: Any, info) -> Any:
        """
        当 Pydantic 给 arguments 赋值时，会自动调用这个函数。

        这里的 3 个参数是 Pydantic 规定的，不用你手动传：
        - cls: 类本身
        - v: 原始值
        - info: 上下文信息
        """

        # 如果传进来的已经是对象了（比如你手动构造时）,直接通过
        if isinstance(v, BaseModel):
            return v

        # 如果是字典，尝试根据工具名转成对应的强类型对象
        if isinstance(v, dict):
            tool_name = info.data.get('name')  # 从上下文拿到工具名

            if tool_name in TOOL_ARG_MAP:
                model_class = TOOL_ARG_MAP[tool_name]
                try:
                    return model_class(**v)  # 实例化成具体的对象
                except Exception:
                    return v  # 实在转不了，就保留字典

        return v

# unity反馈
class UnityFeedback(BaseModel):
    """
    Unity 执行结果反馈
    """
    session_id: str               # 对应的会话ID
    status: Literal["success", "error"] # 执行状态
    message: str                  # 给用户看的信息
    data: Optional[str] = None   # 可选的附加数据

# agent
class AgentResponse(BaseModel):
    """
    这是 Python 发给 Unity 的最终结构
    """
    session_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    thoughts: Optional[str] = None      # 思考过程
    tool_calls: List[ToolCall] = Field(default_factory=list)        # 工具调用列表
    content: Optional[str] = None       # 给用户的自然语言回复（如果没有工具调用）


# ==================== 验证器 ====================

# 映射表：工具名 -> 参数模型
TOOL_ARG_MAP = {
    "create_object": CreateObjectArgs,
    "delete_object": DeleteObjectArgs,
    "modify_object": ModifyObjectArgs,
    "duplicate_object": DuplicateObjectArgs,
    "get_selected_object": GetSelectedObjectArgs,
    "get_scene_objects": GetSceneObjectsArgs,
    "create_material": CreateMaterialArgs,
    "set_material": SetMaterialArgs,
    "attach_script": AttachScriptArgs,
    "modify_script_properties": ModifyScriptPropertiesArgs,
    "create_prefab": CreatePrefabArgs,
    "echo": EchoArgs
}


def validate_tool_calls(response: AgentResponse):
    """校验并转换参数"""
    validated_tools = []
    for call in response.tool_calls:
        arg_model = TOOL_ARG_MAP.get(call.name)
        if arg_model:
            try:
                # 自动校验参数，把 dict 转成对应的 Pydantic 对象
                validated_args = arg_model(**call.arguments)
                validated_tools.append({
                    "name": call.name,
                    "args": validated_args.model_dump()
                })
            except Exception as e:
                print(f"❌ 参数校验失败 {call.name}: {e}")
        else:
            print(f"❌ 未知工具: {call.name}")

    return validated_tools

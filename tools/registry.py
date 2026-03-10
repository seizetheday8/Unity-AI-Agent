from pydantic import BaseModel
import inspect
from typing import Callable, Dict,Optional


class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema 格式


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}  # 工具名 -> 函数
        self.schemas: Dict[str, ToolSchema] = {}  # 工具名 -> 描述

    def register(self, name: str, description: str,parameters_description:Optional[Dict[str, str]] = None):
        """装饰器：注册工具"""

        def decorator(func: Callable):
            # 自动提取参数信息（简化版）
            schema = ToolSchema(
                name=name,
                description=description,
                parameters=self._extract_params(func,parameters_description)  # 需实现参数提取逻辑
            )
            self.tools[name] = func
            self.schemas[name] = schema
            return func

        return decorator

    def _extract_params(self,func: Callable,parameters_description: Optional[Dict[str, str]] = None) -> dict:
        sig = inspect.signature(func)
        params = {}
        for name, param in sig.parameters.items():
            # 获取参数类型（简化处理，实际需更严谨的类型转换）
            param_type = str(param.annotation) if param.annotation != inspect.Parameter.empty else "any"
            # 获取默认值
            default = param.default if param.default != inspect.Parameter.empty else None
            desc = parameters_description.get(name, f"参数 {name}") if parameters_description else f"参数 {name}"
            params[name] = {
                "type": param_type,
                "default": default,
                "description": desc
            }
        return params


# 全局实例
registry = ToolRegistry()

import json
from .registry import registry

def export_tools_json():
    """导出工具列表（供 LLM 调用）"""
    return {
        "tools": [
            {
                "name": schema.name,
                "description": schema.description,
                "parameters": schema.parameters
            }
            for schema in registry.schemas.values()
        ]
    }

def export_tools_md():
    """生成 Markdown 文档（供开发者查看）"""
    md = "# Unity Agent 工具集\n\n"

    for schema in registry.schemas.values():
        md += f"## {schema.name}\n"
        md += f"{schema.description}\n\n"
        md += "**参数**:\n```json\n"
        md += json.dumps(schema.parameters, indent=2, ensure_ascii=False)
        md += "\n```\n\n"

    return md

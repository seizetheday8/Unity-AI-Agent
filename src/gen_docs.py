from tools.export_docs import export_tools_md
from tools import unity_tools

if __name__ == "__main__":
    md_content = export_tools_md()
    with open("../knowledge/TOOLS.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    print("文档已生成到 knowledge/TOOLS.md")
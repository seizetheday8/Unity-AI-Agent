# Unity AI Agent：用自然语言指挥 Unity 编辑器

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![Unity](https://img.shields.io/badge/Unity-2020.3+-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## 📖 项目简介

**Unity AI Agent** 是一个基于大语言模型的**实验性项目**，旨在探索用自然语言控制 Unity 编辑器的可能性。它目前支持**基础的物体创建、材质设置、脚本挂载和属性修改**，并通过 RAG 知识库尝试让系统适应不同的项目规范。

这是一个**持续迭代的框架**，核心架构已经稳定，但功能仍在完善中。你可以把它看作一个**技术原型**，用来体验 AI 辅助游戏开发的潜力，也可以在此基础上扩展自己的工具。

---

## ✨ 核心功能

* ✅ **支持** 用自然语言创建/修改物体
* ✅ **可实现** 材质创建、颜色设置与应用
* ✅ **能够** 挂载已有脚本并修改其字段
* ✅ **提供** 物体复制及批量操作能力
* ✅ **尝试实现** 多步任务自动规划
* ✅ **采用** 分批策略稳定处理大规模任务
* ✅ **集成** RAG 知识库动态适配项目规范
* ✅ **具有** 基础错误恢复与重试机制

---

## 🧰 技术栈

|部分|技术|
|-|-|
|**Python 端**|Python 3.9+, OpenAI (Qwen/DeepSeek API), LangChain, Chroma, Pydantic|
|**Unity 端**|C#, Unity Editor API, Newtonsoft.Json, TCP Socket|
|**通信**|TCP Socket，自定义 JSON 协议|
|**向量库**|Chroma，嵌入模型 paraphrase-multilingual-MiniLM-L12-v2|



---

## 🚀 快速开始

### 环境要求

* Python 3.9 或更高
* Unity 2020.3 或更高（推荐 2022.3 LTS）
* 一个 LLM API Key（支持 OpenAI 格式，如 Qwen、DeepSeek）

### 1\. 克隆仓库

```bash
git clone https://github.com/your-username/unity-ai-agent.git
cd unity-ai-agent
```

### 2\. 配置 Python 环境

安装依赖：

```bash
pip install -r requirements.txt
```

复制环境变量模板并填入你的 API Key：

方法一（手动）：在文件管理器中，将 .env.example 文件复制一份，重命名为 .env，然后用文本编辑器打开并填入你的 API Key。
方法二（命令行）：
在命令提示符或 PowerShell 中运行：

```bash
copy .env.example .env
```

然后用文本编辑器打开 .env 填入你的 Key。

### 3\. 配置 embedding 模型（可选）

本项目使用 HuggingFace 的 paraphrase-multilingual-MiniLM-L12-v2 作为向量模型，首次运行时会自动下载。国内用户如果下载缓慢，可以设置国内镜像：

Windows PowerShell：

```powershell
$env:HF\_ENDPOINT = "https://hf-mirror.com"
```

Windows CMD：

```cmd
set HF\_ENDPOINT=https://hf-mirror.com
```

Linux/macOS：

```bash
export HF\_ENDPOINT=https://hf-mirror.com
```

设置后运行程序，模型将从镜像下载。

如果需要离线使用，可以手动下载模型并指定本地路径

### 4\. 导入 Unity 端脚本

将 Unity/Editor/AI\_agent.cs 复制到你项目的 Assets/Editor 文件夹（如不存在则创建）。

### 5\. 导入测试脚本

将 Unity/Scripts/ 下的示例脚本（StatesController.cs, Rotate.cs）复制到 Assets/Scripts 文件夹。

### 6\. 配置项目规范

系统需要知道你项目中的资源位置（如敌人预制体路径）。在 knowledge/ 目录下：
复制 project\_rules.example.md 为 project\_rules.md。
根据你的项目实际情况，修改 project\_rules.md 中的路径和规范（例如将 Assets/Prefab/Enemy/Skeleton.prefab 改为你项目中的实际路径）。

### 7\. 运行

Unity 端：打开 Unity 编辑器，菜单栏点击 Tools → AI Agent，在打开的窗口中点击“启动服务”。
Python 端：在终端运行：

```bash
python src/Socket.py
```

开始对话：在 Unity 窗口的输入框中输入指令，例如“创建一个红色立方体”，观察结果。

📋 示例指令

|用户指令|系统行为|
|-|-|
|`创建一个红色立方体`|创建 Cube -> 创建材质 -> 设置颜色 -> 应用材质|
|`创建一个等级 3 的敌人 e2`|读取 RAG 规范 -> 实例化预制体 -> 挂载脚本 -> 设置Health/Attack|
|`复制 e2 两次，分别移到 (0,2,0) 和 (2,2,0)`|批量复制 -> 逐个修改坐标|
|`将 e2 的攻击力改为 20`|查找对象 -> 定位脚本组件 -> 修改字段值|
|`生成 3x3x3 魔方，间隔 2 米`|循环规划 27 次创建任务 -> 分批发送执行|


💡 所有指令均支持自然语言变体，系统会自动理解意图。

📁 项目结构  
text  
unity-ai-agent/  
├── src/                      # Python 端核心代码  
│   ├── communication.py      # TCP 通信与消息分发  
│   ├── protocol.py           # Pydantic 数据模型  
│   └── Socket.py             # 主程序入口  
├── tools/                    # 工具注册与实现（Python 包）  
│   ├── `\_\_init\_\_.py`           # 包标识文件  
│   ├── export\_docs.py        # 生成工具列表供 LLM 使用  
│   ├── registry.py           # 工具注册中心  
│   └── unity\_tools.py        # 具体工具函数  
├── knowledge/                # RAG 知识库  
│   ├── project\_rules.example.md  # 示例规范文件（用户需复制修改）  
│   └── project\_rules.md           # 实际使用的规范文件（由用户创建）  
├── Unity/                    # Unity 端脚本  
│   ├── Editor/  
│   │   └── AI\_agent.cs       # 编辑器窗口脚本  
│   └── Scripts/  
│       ├── StatesController.cs    # 示例脚本  
│       └── Rotate.cs         # 示例物体旋转脚本  
├── .env.example              # 环境变量模板  
├── .gitignore                # Git 忽略文件  
├── requirements.txt          # Python 依赖  
└── README.md                 # 本文件

🔧 自定义与扩展

添加新工具

1. 在 tools/unity\_tools.py 中用 @registry.register 装饰器注册新函数。
2. 函数需返回 {"action": "工具名", "params": {...}} 格式。
3. 在 Unity 端的 ExecuteTool 中添加对应的 case 实现具体操作。
4. 重新运行程序，新工具会自动出现在 LLM 的工具列表中。

修改知识库

project\_rules.md 中的内容会被动态注入系统提示，你可以根据项目需求自由增删规范条目。格式为 Markdown，建议保持简洁。

🤝 贡献指南

欢迎任何形式的贡献！如果你发现 bug 或有新功能建议，请：
- 在 GitHub Issues 中搜索是否已存在相关讨论。   
- 若无，请新建 Issue，清晰描述问题或建议。  
- 如果你想直接提交代码，请 fork 仓库，创建新分支，提交 Pull Request。  

📄 许可证

本项目采用 MIT 许可证，详情请见 LICENSE 文件。

🙏 致谢

LLM Providers: Qwen, DeepSeek  
Frameworks: LangChain, Chroma, Pydantic  
Community: 感谢所有开源贡献者  

📌 注意

请勿将你的 API Key 提交到 GitHub，务必在 .gitignore 中忽略 .env 文件。  
所有免费素材（如敌人模型）请用户自行下载，本项目仅提供示例路径，不包含任何可能侵权的资源。  


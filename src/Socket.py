import os
import json
import time
import uuid
from datetime import datetime
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from openai import OpenAI

from src.protocol import AgentResponse
from src.protocol import UserMessage, AssistantMessage, ToolMessage, ToolCallData,Message
from tools.export_docs import export_tools_json
from communication import UnityBridge
# 项目规范md路径
PROJECT_RULES_PATH = "../knowledge/project_rules.md"
# embedding 模型(支持中文)
EMBEDDING_MODEL_PATH = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# LLM模型
MODEL_NAME = "qwen3.5-flash"
# 模型思考模式开关
THINKING_MODE = True

# 最大思考次数
MAX_STEPS = 10
# 最大重试次数
MAX_RETRIES = 3
# 超时时间
BATCH_TIMEOUT = 120

load_dotenv()
qwen_api_key = os.getenv("QWEN_API_KEY")
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

client = OpenAI(
    api_key = qwen_api_key,
    base_url = base_url
)

# 初始化向量库
def init_vectorstore(docuPath:str):
    loader = TextLoader(docuPath, encoding="utf-8")
    docs = loader.load()

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("##", "action_name")],
        strip_headers=False
    )
    md_header_splits = markdown_splitter.split_text(docs[0].page_content)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", " "]
    )
    splits = text_splitter.split_documents(md_header_splits)

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_PATH
    )
    vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings)
    return vectorstore.as_retriever()

def convert_to_api_messages(conversation: list[Message]) -> list[dict]:
    api_messages = []
    for msg in conversation:
        d = msg.model_dump(exclude_none=True)
        if msg.role == "assistant" and msg.tool_calls:
            # 转换为 OpenAI 格式
            api_tool_calls = []
            for tc in msg.tool_calls:
                api_tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                    }
                })
            d["tool_calls"] = api_tool_calls
        api_messages.append(d)
    return api_messages

# 调用LLM
def call_llm(messages: list,retri_project_rules,sys_tools, max_retries = MAX_RETRIES) -> AgentResponse:
    tools_schema = sys_tools

    # 历史消息
    user_content = messages[-1]["content"] if messages[-1]["role"] == "user" else ""

    relevant_rules_docs = retri_project_rules.invoke(user_content)

    project_rules_context = "\n\n".join([doc.page_content for doc in relevant_rules_docs])
    print(f"📏 RAG内容长度: {len(project_rules_context)} 字符")


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

    base_messages = messages  # 原始的对话历史（不含反馈）
    feedbacks = []  # 存储错误反馈

    for attempt in range(max_retries + 1):

        # 构建完整消息列表
        full_messages = [{"role": "system", "content": system_content}] + base_messages + feedbacks

        # llm_log日志 记录请求
        timestamp = datetime.now().isoformat()
        with open("llm_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n--- {timestamp} 请求 ---\n")
            json.dump(full_messages, f, indent=2, ensure_ascii=False)
            f.write("\n")


        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                extra_body={"enable_thinking":THINKING_MODE},
                messages=full_messages,
                stream=False,
                response_format={"type": "json_object"}
            )
            json_str = response.choices[0].message.content

            # llm_log日志 记录响应
            with open("llm_log.txt", "a", encoding="utf-8") as f:
                f.write(f"--- {timestamp} 响应 ---\n")
                f.write(json_str + "\n")

            return AgentResponse.model_validate_json(json_str)

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
                return AgentResponse(
                    thoughts="LLM连续多次响应异常。",
                    content="指令生成失败，请稍后重试或简化请求。"
                )

# 处理Unity输入
def process_user_input(user_input: str, bridge, vectorstore, tools):
    conversation: list[Message] = [UserMessage(content=user_input)]
    step_count = 0
    while step_count < MAX_STEPS:
        print(f"🤔 思考中... (步骤 {step_count+1}/{MAX_STEPS})")
        messages_dict = convert_to_api_messages(conversation)
        response = call_llm(messages_dict, vectorstore, tools)
        if response.thoughts:
            print(f"💭 思考: {response.thoughts}")

        if response.tool_calls:
            # 将助手的工具调用加入对话
            tool_calls_in_msg = [
                ToolCallData(id=f"call_{uuid.uuid4().hex[:8]}", name=tc.name, arguments=tc.arguments.model_dump())
                for tc in response.tool_calls
            ]
            conversation.append(AssistantMessage(tool_calls=tool_calls_in_msg))

            try:
                # 批量发送所有工具调用
                feedback = bridge.send_batch(response.tool_calls, timeout=BATCH_TIMEOUT)
                if feedback.data:
                    results = json.loads(feedback.data)  # 将字符串解析为列表
                else:
                    results = []
                    print("⚠️ 反馈数据为空")

                if len(results) != len(response.tool_calls):
                    print(f"⚠️ 反馈结果数量({len(results)})与工具数量({len(response.tool_calls)})不匹配")
                    # 降级处理：为每个工具生成错误消息
                    for i, tool_call in enumerate(response.tool_calls):
                        tool_call_id = tool_calls_in_msg[i].id
                        conversation.append(ToolMessage(
                            tool_call_id=tool_call_id,
                            name=tool_call.name,
                            content=json.dumps({"status": "error", "message": "反馈结果数量不匹配"})
                        ))
                else:
                    # 按顺序处理每个工具的结果
                    for i, (tool_call, result) in enumerate(zip(response.tool_calls, results)):
                        tool_call_id = tool_calls_in_msg[i].id
                        status = result.get("status", "error")
                        message = result.get("message", "")
                        data = result.get("data")  # 获取可能的附加数据（如物体列表）
                        content_dict = {"status": status, "message": message,
                                        "data": data}
                        content = json.dumps(content_dict, ensure_ascii=False)
                        conversation.append(ToolMessage(
                            tool_call_id=tool_call_id,
                            name=tool_call.name,
                            content=content
                        ))
                        print(f"📦 工具 {tool_call.name}: {status} - {message}")

            except TimeoutError:
                print("⏰ Unity未响应，跳过该批次")
                for i, tool_call in enumerate(response.tool_calls):
                    tool_call_id = tool_calls_in_msg[i].id
                    conversation.append(ToolMessage(
                        tool_call_id=tool_call_id,
                        name=tool_call.name,
                        content=json.dumps({"status": "error", "message": "Unity timeout"})
                    ))

            # 继续循环，让LLM根据反馈决定下一步

        else:
            # 无工具调用，输出最终回复
            if response.content:
                final_msg = response.content
            else:
                final_msg = "任务已完成。"
            # 将最终回复发送给 Unity 显示
            bridge.tcp_send(AgentResponse(content=final_msg).model_dump())
            conversation.append(AssistantMessage(content=final_msg))
            print(f"💬 Agent: {final_msg}")
            break
        step_count += 1
    else:
        print("⚠️ 达到最大步骤限制，强制结束")

if __name__ == "__main__":
    bridge = UnityBridge()
    if not bridge.connect(host="localhost", port=12345):
        exit()

    #项目规范文档
    projRules_vectorstore = init_vectorstore(PROJECT_RULES_PATH)

    #工具库
    sys_tools = export_tools_json()

    print("🤖 Agent 已启动，等待 Unity 指令...")

    try:
        while True:
            # 1. 等待Unity发送指令
            user_input = bridge.wait_for_user_input()
            if not user_input:
                break

            # 重置对话历史
            process_user_input(user_input, bridge, projRules_vectorstore, sys_tools)

    except KeyboardInterrupt:
        print("👋 用户中断")
    finally:
        bridge.disconnect()

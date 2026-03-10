import socket
import time
import json
import uuid
from queue import Queue
from threading import Thread, Event
from typing import List

from src.protocol import UnityFeedback, ToolCall


class UnityBridge:
    RECV_BUFFER_SIZE = 4096
    MAX_PARAMS_LENGTH = 200

    def __init__(self):
        self.socket = None
        self.connected = False
        self.pending_results = {}
        self.result_data = {}
        self.receive_thread = None
        # 用户指令队列
        self.user_input_queue = Queue()

    def connect(self,host="localhost",port=12345,max_retries=10, retry_interval=2):
        for attempt in range(max_retries):
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((host, port))
                self.connected = True
                self.receive_thread = Thread(target=self._receive_loop, daemon=True)
                self.receive_thread.start()
                print("✅ 已连接到 Unity")
                return True
            except Exception as e:
                print(f"⏳ 第 {attempt + 1} 次连接失败，{retry_interval}秒后重试...")
                time.sleep(retry_interval)
        print(f"❌ 连接 Unity 失败，请确保 Unity 服务已启动")
        return False

    def _receive_loop(self):
        """接收数据的循环线程"""
        buffer = b''
        while self.connected:
            try:
                # 接收数据
                data = self.socket.recv(self.RECV_BUFFER_SIZE)
                if not data:
                    break

                buffer += data

                # 每个消息以换行符结束
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    self._dispatch_message(line.decode('utf-8'))

            except Exception as e:
                print(f"❌ 接收错误: {e}")
                break

        self.connected = False

    # 分辨用户指令/Unity反馈
    def _dispatch_message(self, msg:str):
        try:
            data_dict = json.loads(msg)
            if "session_id" in data_dict:
                feedback = UnityFeedback.model_validate(data_dict)
                if feedback.session_id in self.pending_results:
                    self.result_data[feedback.session_id] = feedback
                    self.pending_results[feedback.session_id].set()
            else:
                print(f"📥 收到用户指令: {msg}")
                self.user_input_queue.put(msg)
        except json.JSONDecodeError:
            print(f"📥 收到Unity文本指令: {msg}")
            self.user_input_queue.put(msg)
        except Exception as e:
            print(f"消息处理错误: {e}")

    def disconnect(self):
        if self.socket:
            self.socket.close()
            self.connected = False
            print("🔌 已断开 Unity 连接")

    def wait_for_user_input(self,timeout=None):
        return self.user_input_queue.get(timeout=timeout)

    def tcp_send(self,command: dict):
        try:
            json_data = json.dumps(command)+"\n"
            self.socket.sendall(json_data.encode('utf-8'))

            # 打印 action 日志
            action = command.get('action')
            if not action and 'tool_calls' in command and command['tool_calls']:
                action = command['tool_calls'][0].get('name')
            log_msg = f"📤 发送指令: {action or 'N/A'}"

            # 打印 params 日志
            params = None
            if 'params' in command:
                params = command['params']
            elif 'tool_calls' in command and command['tool_calls']:
                # 只取第一个工具的参数做参考
                params = command['tool_calls'][0].get('arguments')
            if params:
                # 将参数转为 JSON 字符串，并截断过长内容
                params_str = json.dumps(params, ensure_ascii=False)
                if len(params_str) > self.MAX_PARAMS_LENGTH:  # 可根据需要调整长度
                    params_str = params_str[:self.MAX_PARAMS_LENGTH] + "..."
                log_msg += f" 参数: {params_str}"
            print(log_msg)
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            self.disconnect()
            raise

    # 发送单个工具指令
    def send_and_wait(self, tool_call: ToolCall, timeout=50.0):
        session_id = str(uuid.uuid4())
        agent_response = {
            "session_id": session_id,
            "tool_calls": [{
                "name": tool_call.name,
                "arguments": json.dumps(tool_call.arguments.model_dump())
            }]
        }
        self.tcp_send(agent_response)

        # 等待反馈
        event = Event()
        self.pending_results[session_id] = event

        if event.wait(timeout):
            return self.result_data.pop(session_id)
        else:
            raise TimeoutError("Unity 未响应")

    # 发送批量工具指令
    def send_batch(self, tool_calls: List[ToolCall], timeout=60.0) -> UnityFeedback:
        session_id = str(uuid.uuid4())

        tool_calls_data = []
        for tc in tool_calls:
            args_dict = tc.arguments.model_dump()
            # 对 attach_script 的 script_parameters 进行字符串化
            if tc.name == "attach_script" and "script_parameters" in args_dict and args_dict[
                "script_parameters"] is not None:
                # 将 script_parameters 字典转为 JSON 字符串
                args_dict["script_parameters"] = json.dumps(args_dict["script_parameters"], ensure_ascii=False)
            # 对 modify_script_properties 的 new_script_parameters 进行字符串化
            if tc.name == "modify_script_properties" and "new_script_parameters" in args_dict and args_dict[
                "new_script_parameters"] is not None:
                args_dict["new_script_parameters"] = json.dumps(args_dict["new_script_parameters"], ensure_ascii=False)

            tool_calls_data.append({
                "name": tc.name,
                "arguments": json.dumps(args_dict)  # 将参数字典转为 JSON 字符串
            })

        agent_response = {
            "session_id":session_id,
            "tool_calls":tool_calls_data
        }
        self.tcp_send(agent_response)

        event = Event()
        self.pending_results[session_id] = event
        if event.wait(timeout):
            return self.result_data.pop(session_id)
        else:
            raise TimeoutError("Unity 未响应")

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Unity.Plastic.Newtonsoft.Json;
using Unity.Plastic.Newtonsoft.Json.Linq;
using UnityEditor; // 引入编辑器命名空间
using UnityEngine;

public class AgentToolWindow : EditorWindow
{
    private TcpListener server;
    private CancellationTokenSource cts;
    private bool isServerRunning = false;

    // 当前的连接流
    private NetworkStream currentStream;

    // 输入框的内容
    private string inputText = "";

    // 存储日志消息的列表
    private List<string> messageLog = new List<string>();
    // 滚动条位置
    private Vector2 scrollPosition;
    // 用于在后台线程和主线程间传递数据的临时队列
    private readonly object lockObj = new object();
    private Queue<string> incomingMessages = new Queue<string>();

    // AgentCommand类（用于解析JSON）
    [Serializable]
    public class AgentCommand
    {
        public string text;        // echo专用
        public string type;        // create_object专用 (Cube/Sphere)
        public string name;
        public string object_name;
        public string new_object_name;
        public string material_name;
        public string colorHex;   //create_material
        public float[] localScale;
        public float[] localRotation;
        public float[] position;   // create_object专用 [x,y,z]

        public string script_name;
        public string path;
        public string script_parameters;   // JSON 字符串
        public string new_script_parameters;

        public string prefab_name;
    }

    [Serializable]
    public class ToolCall
    {
        public string name;       // create_object
        public string arguments;  // 注意：这里是 JSON 字符串，需要二次解析
    }

    [Serializable]
    public class ToolResult
    {
        public string name;
        public string status; // "success" 或 "error"
        public string message;
        public object data;   // 可选附加数据
    }

    [Serializable]
    public class AgentResponse
    {
        public string session_id;
        public string thoughts;
        public List<ToolCall> tool_calls;
        public string content;
    }

    [Serializable]
    public class UnityFeedback
    {
        public string session_id; // 必须与收到的指令 ID 一致
        public string status;     // "success" 或 "error"
        public string message;    // 详细信息
        public string data;
    }

    [MenuItem("Tools/AI Agent")]
    public static void ShowWindow()
    {
        GetWindow<AgentToolWindow>("AI Agent");
    }
    private void OnEnable()
    {
        // 窗口打开时自动启动
        StartServer();
    }
    private void OnDisable()
    {
        StopServer();
    }

    // 绘制窗口UI
    private void OnGUI()
    {
        // === 顶部控制栏 ===
        GUILayout.Label("AI Agent 服务状态", EditorStyles.boldLabel);

        if (isServerRunning)
        {
            GUI.color = Color.green;
            GUILayout.Label("状态: 运行中...", GUILayout.Height(20));
        }
        else
        {
            GUI.color = Color.red;
            GUILayout.Label("状态: 已停止", GUILayout.Height(20));
        }
        GUI.color = Color.white; // 重置颜色

        // 按钮
        if (GUILayout.Button(isServerRunning ? "停止服务" : "启动服务", GUILayout.Height(20)))
        {
            if (isServerRunning) StopServer();
            else StartServer();
        }

        GUILayout.Space(10);

        // === 消息显示区域 ===
        GUILayout.Label("消息列表:", EditorStyles.boldLabel);

        // 处理来自后台线程的数据
        // 我们在主线程（OnGUI）里把队列里的消息取出来，存到列表里
        lock (lockObj)
        {
            while (incomingMessages.Count > 0)
            {
                string msg = incomingMessages.Dequeue();
                messageLog.Add(msg);

                // 限制日志数量，只保留最近100条
                if (messageLog.Count > 100)
                    messageLog.RemoveAt(0);
            }
        }

        // 开始滚动视图
        scrollPosition = GUILayout.BeginScrollView(scrollPosition, GUILayout.ExpandHeight(true));

        // 绘制每一条消息
        foreach (var log in messageLog)
        {
            GUILayout.Label(log);
        }

        // 如果有新消息，自动滚动到底部
        if (incomingMessages.Count > 0)
        {
            scrollPosition.y = float.MaxValue;
        }

        GUILayout.EndScrollView();

        // === 底部输入区 (这是新增的核心代码) ===
        GUILayout.Space(5);

        // 画一条分割线
        GUILayout.Box("", GUILayout.Height(2), GUILayout.ExpandWidth(true));

        EditorGUILayout.BeginHorizontal();
        {
            // 1. 输入框
            GUI.SetNextControlName("ChatInput");
            inputText = EditorGUILayout.TextField(inputText, GUILayout.Height(25));

            // 2. 发送按钮
            GUI.enabled = (currentStream != null);
            if (GUILayout.Button("发送", GUILayout.Width(60), GUILayout.Height(25)))
            {
                SendToPython();
            }
            GUI.enabled = true;
        }
        EditorGUILayout.EndHorizontal();

        // 3. 捕捉回车键
        if (Event.current.isKey && Event.current.keyCode == KeyCode.Return)
        {
            if (GUI.GetNameOfFocusedControl() == "ChatInput" && !string.IsNullOrEmpty(inputText))
            {
                SendToPython();
                Event.current.Use(); // 防止换行
            }
        }

        // 清空日志按钮
        if (GUILayout.Button("清空日志"))
        {
            messageLog.Clear();
        }
    }

    private void StartServer()
    {
        if (isServerRunning) return;

        try
        {
            cts = new CancellationTokenSource();
            server = new TcpListener(IPAddress.Parse("127.0.0.1"), 12345);
            server.Start();
            isServerRunning = true;

            // 记录一条系统日志
            AddLog("服务器已启动 (端口 12345)");

            _ = ListenForClientsAsync(cts.Token);
        }
        catch (Exception e)
        {
            AddLog($"启动失败: {e.Message}");
        }
    }
    private void StopServer()
    {
        if (!isServerRunning) return;

        cts?.Cancel();
        server?.Stop();
        isServerRunning = false;

        AddLog("服务器已停止");
    }

    // 辅助方法：线程安全地添加日志
    private void AddLog(string message)
    {
        // 加锁防止多线程冲突
        lock (lockObj)
        {
            // 添加时间戳
            string time = DateTime.Now.ToString("HH:mm:ss");
            incomingMessages.Enqueue($"[{time}] {message}");
        }

        // 请求重绘窗口
        EditorApplication.delayCall += () => Repaint();
    }

    private async Task ListenForClientsAsync(CancellationToken token)
    {
        try
        {
            while (!token.IsCancellationRequested)
            {
                TcpClient client = await server.AcceptTcpClientAsync();
                AddLog("Python 客户端已连接");

                _ = HandleClientAsync(client, token);
            }
        }
        catch (ObjectDisposedException) {
            AddLog("连接已关闭，停止接收");
        }
        catch (Exception e)
        {
            AddLog($"监听异常: {e.Message}");
        }
    }

    private async Task HandleClientAsync(TcpClient client, CancellationToken token)
    {
        currentStream = client.GetStream();

        AddLog("Python 已连接，现在可以双向交互了。");

        using (currentStream)
        {
            byte[] buffer = new byte[4096];
            while (!token.IsCancellationRequested)
            {
                int bytesRead = await currentStream.ReadAsync(buffer, 0, buffer.Length, token);
                if (bytesRead == 0) break;

                string json = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                
                string feedbackJson = ExecuteCommand(json,currentStream);

                // 反馈
                if (!string.IsNullOrEmpty(feedbackJson))
                {
                    byte[] feedbackData = Encoding.UTF8.GetBytes(feedbackJson + "\n");
                    await currentStream.WriteAsync(feedbackData, 0, feedbackData.Length, token);
                }
            }
        }

        currentStream = null;
        AddLog("Python 断开连接");
    }

    // 命令执行
    string ExecuteCommand(string json,NetworkStream stream)
    {
        try
        {
            var response = JsonUtility.FromJson<AgentResponse>(json);
            string sessionId = response.session_id;

            // 核心改动：循环执行所有工具调用
            if (response.tool_calls != null && response.tool_calls.Count > 0)
            {
                bool allSuccess = true;
                List<string> resultMessages = new List<string>();
                List<ToolResult> results = new List<ToolResult>();

                foreach (var call in response.tool_calls)
                {
                    AgentCommand cmdArgs = JsonUtility.FromJson<AgentCommand>(call.arguments);
                    var (success, msg, data) = ExecuteTool(call.name, cmdArgs);
                    AddLog(msg);
                    if (!success) allSuccess=false;
                    results.Add(new ToolResult
                    {
                        name = call.name,
                        status = success ? "success" : "error",
                        message = msg,
                        data = data
                    });
                }
                string combinedMessage = string.Join("; ", results.Select(r => r.message));
                return JsonUtility.ToJson(new UnityFeedback
                {
                    session_id = sessionId,
                    status = allSuccess ? "success" : "error",
                    message = combinedMessage,
                    data = JsonConvert.SerializeObject(results)
                });

            }
            else
            {
                // 普通聊天或最终服务
                if (!string.IsNullOrEmpty(response.content))
                {
                    AddLog($"[Agent] {response.content}");
                }
                return JsonUtility.ToJson(new UnityFeedback
                {
                    session_id = sessionId,
                    status = "success",
                    message = "已收到消息",
                    data = null
                });
            }
        }
        catch (Exception e)
        {
            return JsonUtility.ToJson(new UnityFeedback
            {
                session_id = "unknown",
                status = "error",
                message = $"解析异常: {e.Message}",
                data = null
            });
        }
    }
    // 工具调用 
    (bool success, string message,object data) ExecuteTool(string toolName, AgentCommand args)
    {
        switch (toolName)
        {
            case "echo":
                {
                    AddLog($"[Agent] {args.text}");
                    return (true, "执行成功",null);
                }
            case "create_object":
                {
                    GameObject obj;

                    //判断类型
                    if (args.type == "Sphere")
                        obj = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                    else if(args.type == "Cube")
                        obj = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    else if(args.type == "Cylinder")
                        obj= GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                    else if( args.type == "Capsule")
                        obj = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                    else if(args.type == "Plane")
                        obj = GameObject.CreatePrimitive(PrimitiveType.Plane);
                    else if (args.type == "Quad")
                        obj = GameObject.CreatePrimitive(PrimitiveType.Quad);
                    else
                        obj= GameObject.CreatePrimitive(PrimitiveType.Cube);

                    if (!string.IsNullOrEmpty(args.object_name))
                        obj.name = args.object_name;

                    if (args.localScale != null && args.localScale.Length == 3)
                        obj.transform.localScale = new Vector3(args.localScale[0], args.localScale[1], args.localScale[2]);

                    if (args.position != null && args.position.Length == 3)
                        obj.transform.position = new Vector3(args.position[0], args.position[1], args.position[2]);

                    if (args.localRotation != null && args.localRotation.Length == 3)
                        obj.transform.localRotation = Quaternion.Euler(args.localRotation[0], args.localRotation[1], args.localRotation[2]);
              
                    // 选中创建完的物体
                    Selection.activeGameObject = obj; 
                    return (true, $"执行成功: 创建了 {obj.name} 物体",null);
                }
            case "modify_object":
                {
                    GameObject obj = GameObject.Find(args.object_name);
                    if (obj == null)
                        return (false, $"执行失败: 未找到物体 '{args.object_name}'", null);

                    if (args.new_object_name != null)
                    {
                        obj.name = args.new_object_name;
                    }

                    if (args.position != null && args.position.Length == 3)
                        obj.transform.position = new Vector3(args.position[0], args.position[1], args.position[2]);

                    if (args.localRotation != null && args.localRotation.Length == 3)
                        obj.transform.localRotation = Quaternion.Euler(args.localRotation[0], args.localRotation[1], args.localRotation[2]);

                    if (args.localScale != null && args.localScale.Length == 3)
                        obj.transform.localScale = new Vector3(args.localScale[0], args.localScale[1], args.localScale[2]);

                    // 选中修改后的物体
                    Selection.activeGameObject = obj;

                    return (true, $"执行成功: 已修改物体 '{obj.name}'", null);
                }
            case "delete_object":
                {
                    // 安全检查：防止删除关键物体
                    string[] protectedNames = { "Main Camera", "Directional Light" };
                    if (protectedNames.Contains(args.object_name))
                    {
                        return (false, $"执行失败: 禁止删除关键物体 '{args.object_name}'", null);
                    }

                    GameObject obj = GameObject.Find(args.object_name);
                    if (obj == null)
                        return (false, $"执行失败: 未找到物体 '{args.object_name}'", null);

                    string objName = obj.name;
                    GameObject.DestroyImmediate(obj); // 在编辑器下立即销毁

                    return (true, $"执行成功: 已删除物体 '{objName}'", null);
                }
            case "duplicate_object":
                {
                    GameObject original = GameObject.Find(args.object_name);
                    if (original == null)
                        return (false, $"未找到物体 '{args.object_name}'", null);

                    GameObject clone = GameObject.Instantiate(original);

                    // 复制
                    if (args.position != null && args.position.Length == 3)
                        clone.transform.position = new Vector3(args.position[0], args.position[1], args.position[2]);

                    if (args.localRotation != null && args.localRotation.Length == 3)
                        clone.transform.localRotation = Quaternion.Euler(args.localRotation[0], args.localRotation[1], args.localRotation[2]);

                    if (args.localScale != null && args.localScale.Length == 3)
                        clone.transform.localScale = new Vector3(args.localScale[0], args.localScale[1], args.localScale[2]);

                    // 设置新名称
                    if (!string.IsNullOrEmpty(args.new_object_name))
                        clone.name = args.new_object_name;

                    Selection.activeGameObject = clone;
                    return (true, $"已复制物体 '{args.object_name}' 为 '{clone.name}'", null);
                }
            case "get_selected_object":
                {
                    GameObject selected = Selection.activeGameObject;
                    string selectedName = selected != null ? selected.name : "";
                    return (true, $"当前选中物体: '{selectedName}'", null);
                }
            case "get_scene_objects":
                {
                    GameObject[] allObjects = GameObject.FindObjectsOfType<GameObject>();
                    int maxCount = 50;
                    var objectsList = new List<object>();
                    for (int i = 0; i < Mathf.Min(allObjects.Length, maxCount); i++)
                    {
                        GameObject obj = allObjects[i];
                        string type = "Unknown";
                        // 尝试判断物体类型
                        MeshFilter mf = obj.GetComponent<MeshFilter>();
                        if (mf != null && mf.sharedMesh != null)
                        {
                            if (mf.sharedMesh.name.Contains("Cube"))
                                type = "Cube";
                            else if (mf.sharedMesh.name.Contains("Sphere"))
                                type = "Sphere";
                            else if (mf.sharedMesh.name.Contains("Cylinder"))
                                type = "Cylinder";
                            else if (mf.sharedMesh.name.Contains("Capsule"))
                                type = "Capsule";
                            else if (mf.sharedMesh.name.Contains("Plane"))
                                type = "Plane";
                            else if (mf.sharedMesh.name.Contains("Quad"))
                                type = "Quad";
                        }
                        objectsList.Add(new { name = obj.name, type = type });
                    }
                    // 返回结构化数据
                    var data = new { objects = objectsList };
                    string message = $"场景物体 ({objectsList.Count} 个)";
                    return (true, message, data);
                }
            case "create_material":
                {
                    // 创建材质对象
                    Material mat = new Material(Shader.Find("Standard"));
                    mat.name = name;

                    // 处理颜色
                    if (!string.IsNullOrEmpty(args.colorHex))
                    {
                        if (ColorUtility.TryParseHtmlString(args.colorHex, out Color color))
                            mat.color = color;
                    }
                    else
                    {
                        mat.color = Color.white;
                    }

                    // 默认材质存放路径
                    string folderPath = "Assets/Material";
                    if (!AssetDatabase.IsValidFolder(folderPath))
                    {
                        AssetDatabase.CreateFolder("Assets", "Material");
                    }

                    string assetPath = $"{folderPath}/{name}.mat";

                    // 
                    if (File.Exists(assetPath))
                    {
                        return (false, $"执行失败:材质已存在: {args.material_name}，请更改名称", null);
                    }

                    // 生成资源
                    AssetDatabase.CreateAsset(mat, assetPath);
                    AssetDatabase.SaveAssets();
                    AssetDatabase.Refresh();

                     return (true, $"执行成功: 创建了{args.material_name} 材质", null);
                }
            case "set_material":
                {
                    GameObject obj = GameObject.Find(args.object_name);
                    if (obj == null)
                    {
                        return (false, $"执行失败: 未找到物体 '{args.object_name}'", null);
                    }

                    // 通过名称查找材质
                    Material mat = Resources.FindObjectsOfTypeAll<Material>()
                        .FirstOrDefault(m => m.name == args.material_name);
                    if (mat == null) {
                        return (false, $"执行失败: 未找到材质 '{args.material_name}'", null);
                    }

                    Renderer renderer = obj.GetComponent<Renderer>();
                    if (renderer == null)
                    {
                        renderer = obj.AddComponent<MeshRenderer>(); 
                    }
                    renderer.sharedMaterial = mat;
                    return (true, $"执行成功: 已为物体 '{args.object_name}' 设置材质 '{args.material_name}'", null);
                }
            case "attach_script":
                {
                    if (args.object_name == null)
                        return (false, "执行失败: object_name为空", null);
                    GameObject obj = GameObject.Find(args.object_name);
                    if (obj == null)
                        return (false, $"执行失败:  未找到物体 '{args.object_name}'", null);
                    if (EditorApplication.isCompiling)
                    {
                        return (false, "执行失败:  Unity 正在编译，请稍后重试", null);
                    }
                    // 获取主程序集
                    System.Reflection.Assembly assembly = System.Reflection.Assembly.Load("Assembly-CSharp");
                    if (assembly == null)
                        return (false, "执行失败:  无法加载主程序集", null);
                    if (args.script_name == null)
                        return (false, "执行失败: script_name为空", null);

                    Type scriptType = assembly.GetType(args.script_name);
                    if (scriptType == null)
                    {
                        scriptType = Type.GetType(args.script_name);
                    }
                    if (scriptType == null) {
                        return (false, $"执行失败:  未找到脚本 '{args.script_name}'", null);
                    }
                    if (obj.GetComponent(scriptType) != null)
                    {
                        return (false, $"物体 '{args.object_name}' 已挂载过脚本 '{args.script_name}'", null);
                    }
                    Component comp = obj.AddComponent(scriptType);

                    if (!string.IsNullOrEmpty(args.script_parameters))
                    {
                        try
                        {
                            JObject parameters = JObject.Parse(args.script_parameters);
                            foreach (var prop in parameters.Properties())
                            {
                                var field = scriptType.GetField(prop.Name);
                                if (field != null)
                                {
                                    object value = prop.Value.ToObject(field.FieldType);
                                    field.SetValue(comp, value);
                                }
                            }
                        }
                        catch (Exception e)
                        {
                            Debug.LogWarning($"参数解析失败: {e.Message}");
                        }
                    }
                    return (true, $"执行成功: 已为物体 '{args.object_name}' 挂载脚本 '{args.script_name}'", null);
                }
            case "modify_script_properties":
                {
                    if (args.object_name == null)
                        return (false, "执行失败: object_name为空", null);
                    GameObject obj = GameObject.Find(args.object_name);
                    if (obj == null)
                        return (false, $"执行失败:  未找到物体 '{args.object_name}'", null);

                    Type targetScriptType = Type.GetType(args.script_name + ",Assembly-CSharp") ?? Type.GetType(args.script_name);
                    if (targetScriptType == null)
                        return (false, $"未找到脚本类型 '{args.script_name}'", null);

                    Component targetComponent = obj.GetComponent(targetScriptType);
                    if (targetComponent == null)
                        return (false, $"物体 '{args.object_name}' 上没有挂载脚本 '{args.script_name}'", null);

                    // 解析 new_script_parameters 字符串
                    if (string.IsNullOrEmpty(args.new_script_parameters))
                        return (false, "未提供任何属性", null);

                    JObject props;
                    try
                    {
                        props = JObject.Parse(args.new_script_parameters);
                    }
                    catch
                    {
                        return (false, "属性格式无效，应为 JSON 对象", null);
                    }

                    List<string> setFields = new List<string>();
                    foreach (var prop in props.Properties())
                    {
                        var field = targetScriptType.GetField(prop.Name);
                        if (field == null)
                        {
                            AddLog($"脚本 '{targetScriptType.Name}' 上没有找到字段 '{prop.Name}'，跳过");
                            continue;
                        }
                        try
                        {
                            object value = prop.Value.ToObject(field.FieldType);
                            field.SetValue(targetComponent, value);
                            setFields.Add($"{prop.Name}={value}");
                        }
                        catch (Exception e)
                        {
                            AddLog($"设置字段 '{prop.Name}' 失败: {e.Message}");
                        }
                    }

                    if (setFields.Count == 0)
                        return (false, "没有成功设置任何属性", null);

                    return (true, $"已修改物体 '{args.object_name}' 的脚本属性: {string.Join(", ", setFields)}", null);
                }
            case "create_prefab":
                {
                    string fullPath = args.path+"/"+args.prefab_name+".prefab";
                    GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(fullPath);
                    if (prefab == null)
                        return (false, $"执行失败:  未找到预制体: {fullPath}", null);

                    // 实例化
                    GameObject instance = PrefabUtility.InstantiatePrefab(prefab) as GameObject;
                    if (instance == null)
                        return (false, "执行失败:  实例化失败", null);

                    // 设置名称
                    if (!string.IsNullOrEmpty(args.object_name))
                        instance.name = args.object_name;

                    if (args.localScale != null && args.localScale.Length == 3)
                        instance.transform.localScale = new Vector3(args.localScale[0], args.localScale[1], args.localScale[2]);

                    if (args.position != null && args.position.Length == 3)
                        instance.transform.position = new Vector3(args.position[0], args.position[1], args.position[2]);

                    if (args.localRotation != null && args.localRotation.Length == 3)
                        instance.transform.localRotation = Quaternion.Euler(args.localRotation[0], args.localRotation[1], args.localRotation[2]);

                    Selection.activeGameObject = instance;

                    return (true, $"执行成功: 通过 {args.prefab_name}预制体创建了实例，命名为{args.object_name} ", null);
                }
            default:
                return (false, $"执行失败:  未知工具: {toolName}", null);
        }
    }

    private void SendToPython()
    {
        if (string.IsNullOrEmpty(inputText)) return;
        if (currentStream == null)
        {
            AddLog("未连接，无法发送");
            return;
        }

        try
        {
            // 1. 把文字转成字节流
            byte[] data = Encoding.UTF8.GetBytes(inputText + "\n");

            // 2. 发送
            currentStream.WriteAsync(data, 0, data.Length);

            // 3. 在自己的窗口里显示一下（留底）
            AddLog($"[Unity] {inputText}");

            // 4. 清空输入框
            inputText = "";
        }
        catch (Exception e)
        {
            AddLog($"❌ 发送失败: {e.Message}");
        }
    }
}


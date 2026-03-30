using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Unity.Plastic.Newtonsoft.Json;
using Unity.Plastic.Newtonsoft.Json.Linq;
using UnityEditor; // 引入编辑器命名空间
using UnityEngine;
using UnityEngine.Networking;

public static class UnityWebRequestAwaiterExtension
{
    public static TaskAwaiter<UnityWebRequest.Result> GetAwaiter(this UnityWebRequestAsyncOperation asyncOp)
    {
        var tcs = new TaskCompletionSource<UnityWebRequest.Result>();
        asyncOp.completed += _ =>
        {
            // 请求完成后，通过 asyncOp.webRequest 获取结果
            if (asyncOp.webRequest != null)
            {
                tcs.SetResult(asyncOp.webRequest.result);
            }
            else
            {
                // 正常情况下 webRequest 应该存在，但以防万一
                tcs.SetResult(UnityWebRequest.Result.ConnectionError);
            }
        };
        return tcs.Task.GetAwaiter();
    }
}
public class AgentToolWindow : EditorWindow
{
    private string apiUrl = "http://localhost:8000/execute";
    private List<Dictionary<string, object>> history = new List<Dictionary<string, object>>();
    private bool isProcessing = false;                    // 防止重复请求

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
        public string id;
        public string name;       // create_object
        public string arguments;  // 注意：这里是 JSON 字符串，需要二次解析
    }

    [Serializable]
    public class AgentResponse
    {
        public string session_id;
        public string thoughts;
        public List<ToolCall> tool_calls;
        public string content;
    }

    [MenuItem("Tools/AI Agent")]
    public static void ShowWindow()
    {
        GetWindow<AgentToolWindow>("AI Agent");
    }
    private void OnEnable()
    {
        // 窗口打开时自动启动
        LoadHistory();
    }
    private void OnDisable()
    {
        SaveHistory();
    }
    // 绘制窗口UI
    private void OnGUI()
    {
        // === 顶部控制栏 ===
        GUILayout.Label("AI Agent 服务状态", EditorStyles.boldLabel);
        GUI.color = Color.green;
        GUILayout.Label($"API 地址: {apiUrl}", GUILayout.Height(20));
        GUI.color = Color.white;


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
            //GUI.enabled = (currentStream != null);
            if (GUILayout.Button("发送", GUILayout.Width(60), GUILayout.Height(25)))
            {
                SendToAgent(inputText);
            }
            GUI.enabled = true;
        }
        // 3. 捕捉回车键
        if (Event.current.isKey && Event.current.keyCode == KeyCode.Return)
        {
            if (GUI.GetNameOfFocusedControl() == "ChatInput" && !string.IsNullOrEmpty(inputText))
            {
                SendToAgent(inputText);
                Event.current.Use(); // 防止换行
            }
        }
        if (GUILayout.Button("清空日志", GUILayout.Height(20)))
        {
            messageLog.Clear();
        }
        if (GUILayout.Button("清空会话", GUILayout.Height(20)))
        {
            ClearHistory();
        }
        EditorGUILayout.EndHorizontal();
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

                    string msg = $"执行成功: 创建了 {obj.name} 物体";

                    if (args.localScale != null && args.localScale.Length == 3) {
                        obj.transform.localScale = new Vector3(args.localScale[0], args.localScale[1], args.localScale[2]);
                        msg += $"，大小 [{args.localScale[0]:F2}, {args.localScale[1]:F2}, {args.localScale[2]:F2}]";
                    }
                    if (args.position != null && args.position.Length == 3) {
                        obj.transform.position = new Vector3(args.position[0], args.position[1], args.position[2]);
                        msg += $"，位置 [{args.position[0]:F2}, {args.position[1]:F2}, {args.position[2]:F2}]";
                    }
                    if (args.localRotation != null && args.localRotation.Length == 3)
                    {
                        obj.transform.localRotation = Quaternion.Euler(args.localRotation[0], args.localRotation[1], args.localRotation[2]);
                        msg += $"，旋转 [{args.localRotation[0]:F2}°, {args.localRotation[1]:F2}°, {args.localRotation[2]:F2}°]";
                    }
                    // 选中创建完的物体
                    Selection.activeGameObject = obj;

                    return (true, msg, null);
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

                    string msg = $"执行成功: 已修改物体 '{args.object_name}'名称为'{args.new_object_name}'";

                    if (args.localScale != null && args.localScale.Length == 3) {
                        obj.transform.localScale = new Vector3(args.localScale[0], args.localScale[1], args.localScale[2]);
                        msg += $"，大小 [{args.localScale[0]:F2}, {args.localScale[1]:F2}, {args.localScale[2]:F2}]";
                    }
                    if (args.position != null && args.position.Length == 3) {
                        obj.transform.position = new Vector3(args.position[0], args.position[1], args.position[2]);
                        msg += $"，位置 [{args.position[0]:F2}, {args.position[1]:F2}, {args.position[2]:F2}]";
                    }
                    if (args.localRotation != null && args.localRotation.Length == 3)
                    {
                        obj.transform.localRotation = Quaternion.Euler(args.localRotation[0], args.localRotation[1], args.localRotation[2]);
                        msg += $"，旋转 [{args.localRotation[0]:F2}°, {args.localRotation[1]:F2}°, {args.localRotation[2]:F2}°]";
                    }

                    // 选中修改后的物体
                    Selection.activeGameObject = obj;

                    return (true, msg, null);
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

                    // 设置新名称
                    if (!string.IsNullOrEmpty(args.new_object_name))
                        clone.name = args.new_object_name;

                    string msg = $"执行成功: 已复制物体 '{args.object_name}',新物体'{args.new_object_name}'";

                    if (args.localScale != null && args.localScale.Length == 3)
                    {
                        clone.transform.localScale = new Vector3(args.localScale[0], args.localScale[1], args.localScale[2]);
                        msg += $"，新大小 [{args.localScale[0]:F2}, {args.localScale[1]:F2}, {args.localScale[2]:F2}]";
                    }
                    if (args.position != null && args.position.Length == 3)
                    {
                        clone.transform.position = new Vector3(args.position[0], args.position[1], args.position[2]);
                        msg += $"，新位置 [{args.position[0]:F2}, {args.position[1]:F2}, {args.position[2]:F2}]";
                    }
                    if (args.localRotation != null && args.localRotation.Length == 3)
                    {
                        clone.transform.localRotation = Quaternion.Euler(args.localRotation[0], args.localRotation[1], args.localRotation[2]);
                        msg += $"，新旋转 [{args.localRotation[0]:F2}°, {args.localRotation[1]:F2}°, {args.localRotation[2]:F2}°]";
                    }

                    Selection.activeGameObject = clone;
                    return (true, msg, null);
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
                    mat.name = args.material_name;

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

                    string assetPath = $"{folderPath}/{args.material_name}.mat";

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
                    else
                    {
                            return (false, "未提供任何初始属性", null);
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
    private void SendToAgent(string userInput)
    {
        if (string.IsNullOrEmpty(userInput)) return;
        if (isProcessing)
        {
            AddLog("正在处理上一轮，请稍后再试。");
            return;
        }

        // 将用户输入加入历史
        history.Add(new Dictionary<string, object> { ["role"] = "user", ["content"] = userInput });
        SaveHistory();
        AddLog($"[Unity] {userInput}");
        inputText = "";

        _ = SendRequestAsync();
    }
    private async Task SendRequestAsync()
    {
        if (isProcessing) return;
        isProcessing = true;

        string historyJson = JsonConvert.SerializeObject(history);
        for (int i = 0; i < history.Count; i++)
        {
            var item = history[i];
        }
        try
        {
            var requestBody = new { history = history };
            string json = JsonConvert.SerializeObject(requestBody);
            using (UnityWebRequest req = new UnityWebRequest(apiUrl, "POST"))
            {
                byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);
                req.uploadHandler = new UploadHandlerRaw(bodyRaw);
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");

                var result = await req.SendWebRequest();

                if (result != UnityWebRequest.Result.Success)
                {
                    AddLog($"HTTP 错误: {req.error}");
                    return;
                }
                AgentResponse resp = JsonConvert.DeserializeObject<AgentResponse>(req.downloadHandler.text);
                if (resp == null) { AddLog("响应解析失败"); return; }

                ProcessResponse(resp);
            }
        }
        catch (Exception e) { AddLog($"异常: {e.Message}"); }
        finally { isProcessing = false; }
    }
    // 处理响应（工具调用或最终回复）
    private void ProcessResponse(AgentResponse resp)
    {
        if (resp.tool_calls != null && resp.tool_calls.Count > 0)
        {
            // 1. 添加 assistant 消息（带 tool_calls）
            var toolCallsList = new List<Dictionary<string, object>>();
            foreach (var tc in resp.tool_calls)
            {
                toolCallsList.Add(new Dictionary<string, object>
                {
                    ["id"] = tc.id,
                    ["name"] = tc.name,
                    ["arguments"] = tc.arguments
                });
            }
            history.Add(new Dictionary<string, object> { ["role"] = "assistant", ["tool_calls"] = toolCallsList });
            SaveHistory();

            foreach (var call in resp.tool_calls)
            {
                AgentCommand args = JsonUtility.FromJson<AgentCommand>(call.arguments);
                var (success, msg, data) = ExecuteTool(call.name, args);
                AddLog(msg);

                var toolMsg = new Dictionary<string, object>
                {
                    ["role"] = "tool",
                    ["tool_call_id"] = call.id,
                    ["name"] = call.name,
                    ["content"] = JsonConvert.SerializeObject(new { status = success ? "success" : "error", message = msg, data = data })
                };
                history.Add(toolMsg);
            }
            SaveHistory();

            if (history.Count > 30) { AddLog("达到最大步骤限制，停止。"); return; }
            isProcessing = false;
            _ = SendRequestAsync(); // 继续下一轮
        }
        else if (!string.IsNullOrEmpty(resp.content))
        {
            AddLog($"[Agent] {resp.content}");
            history.Add(new Dictionary<string, object> { ["role"] = "assistant", ["content"] = resp.content });
            SaveHistory();
        }
        else AddLog("响应内容为空");
    }
    private void LoadHistory()
    {
        if (EditorPrefs.HasKey("Agent_History"))
        {
            string json = EditorPrefs.GetString("Agent_History");
            history = JsonConvert.DeserializeObject<List<Dictionary<string, object>>>(json) ?? new List<Dictionary<string, object>>();
        }
        else
        {
            history = new List<Dictionary<string, object>>();
        }
    }
    private void SaveHistory()
    {
        string json = JsonConvert.SerializeObject(history);
        EditorPrefs.SetString("Agent_History", json);
    }
    private void ClearHistory()
    {
        history.Clear();
        EditorPrefs.DeleteKey("Agent_History");
        AddLog("会话历史已清空");
    }
}


import json
from .registry import registry

# ==================== 物体操作类 ====================

@registry.register(
    name="create_object",
    description="在 Unity 场景中创建一个基础几何体（无材质）,创建完会选中",
    parameters_description={
        "type": "几何体类型（Cube/Sphere/Capsule/Cylinder/Plane/Quad）",
        "object_name": "物体名称",
        "position": "位置坐标，格式为[x,y,z]（可选，默认 [0,0,0]）",
        "localRotation": "局部旋转欧拉角 [x, y, z]（可选，默认 [0,0,0]）",
        "localScale": "缩放比例，格式为[x,y,z]（可选，默认 [1,1,1]）",
    }

)
def tool_create_object(
        object_name: str,
        type: str = "Cube",
        position: list = [0, 0, 0],
        localRotation: list = [0, 0, 0],
        localScale: list = [1, 1, 1]
) -> dict:
    """返回符合协议的指令字典"""
    return {
        "action": "create_object",
        "params": {
            "object_name": object_name,
            "type": type,
            "position": position,
            "localRotation": localRotation,
            "localScale": localScale
        }
    }

@registry.register(
    name="delete_object",
    description="删除指定物体（安全检查会阻止删除关键物体如 Main Camera）",
    parameters_description={
        "object_name": "要删除的物体名称"
    }
)
def tool_delete_object(
        object_name: str
) -> dict:
    """删除物体"""
    return {
        "action": "delete_object",
        "params": {
            "object_name": object_name
        }
    }

@registry.register(
    name="modify_object",
    description="修改指定物体的属性（名字、位置、旋转、缩放），只需提供要修改的字段",
    parameters_description={
        "object_name": "要修改的原物体名称",
        "new_object_name": "修改后的物体名称",
        "position": "新的位置坐标 [x, y, z]（可选）",
        "localRotation": "新的局部旋转欧拉角 [x, y, z]（可选）",
        "localScale": "新的局部缩放 [x, y, z]（可选）"
    }
)
def tool_modify_object(
        object_name: str,
        new_object_name: str = None,
        position: list = None,
        localRotation: list = None,
        localScale: list = None
) -> dict:
    """修改物体属性，只包含非 None 的字段"""
    params = {"object_name": object_name}
    if new_object_name is not None:
        params["new_object_name"] = new_object_name
    if position is not None:
        params["position"] = position
    if localRotation is not None:
        params["localRotation"] = localRotation
    if localScale is not None:
        params["localScale"] = localScale
    return {
        "action": "modify_object",
        "params": params
    }

@registry.register(
    name="duplicate_object",
    description="复制指定物体,会完整保留原物体的所有组件、挂载的脚本以及脚本中的字段值（深拷贝）,并可设置新名称、位置、旋转、缩放（若未指定则与原物体相同）",
    parameters_description={
        "object_name": "要复制的物体名称",
        "new_object_name": "新物体名称（可选）",
        "position": "新的位置坐标 [x, y, z]（可选）",
        "localRotation": "新的局部旋转欧拉角 [x, y, z]（可选）",
        "localScale": "新的局部缩放 [x, y, z]（可选）"
    }
)
def tool_duplicate_object(object_name: str, new_object_name: str = None, position: list = None, localRotation: list = None, localScale: list = None) -> dict:
    params = {"object_name": object_name}
    if new_object_name:
        params["new_object_name"] = new_object_name
    if position:
        params["position"] = position
    if localRotation:
        params["localRotation"] = localRotation
    if localScale:
        params["localScale"] = localScale
    return {
        "action": "duplicate_object",
        "params": params
    }
# ==================== 查询类 ====================
@registry.register(
    name="get_selected_object",
    description="获取当前在Unity场景中选中的物体名称（如果没有选中物体，返回空字符串）",
    parameters_description={}
)
def tool_get_selected_object() -> dict:
    """返回获取选中物体的指令"""
    return {
        "action": "get_selected_object",
        "params": {}
    }

@registry.register(
    name="get_scene_objects",
    description="获取当前Unity场景中所有物体的名称列表（最多返回50个）",
    parameters_description={}  # 无参数
)
def tool_get_scene_objects() -> dict:
    """返回获取场景物体的指令"""
    return {
        "action": "get_scene_objects",
        "params": {}
    }


#  ==================== 材质操作类 ====================
@registry.register(
    name="create_material",
    description="仅创建一个材质，无其它操作",
    parameters_description={
        "material_name":"材质名称",
        "colorHex":"颜色十六进制值,如#FFFFFF"
    }
)
def tool_create_material(
        material_name: str,
        colorHex: str = "#FFFFFF"
) -> dict:
    return {
        "action": "create_material",
        "params": {
            "material_name": material_name,
            "colorHex": colorHex,
        }
    }

@registry.register(
    name="set_material",
    description="为指定物体设置现有材质（材质必须已存在，否则会失败）",
    parameters_description={
        "object_name": "要设置材质的物体名称",
        "material_name": "材质名称（需已存在于项目中）"
    }
)
def tool_set_material(object_name: str, material_name: str) -> dict:
    return {
        "action": "set_material",
        "params": {
            "object_name": object_name,
            "material_name": material_name
        }
    }

#  ==================== 脚本类 ====================
@registry.register(
    name="attach_script",
    description="将脚本挂载到指定物体上，并可设置脚本的公共字段参数",
    parameters_description={
        "object_name": "目标物体名称",
        "script_name": "脚本名称（不带 .cs）",
        "script_parameters": "脚本参数，字典形式，键为字段名，值为字段值（可选）"
    }
)
def tool_attach_script(
        object_name: str,
        script_name: str,
        script_parameters: dict = None
) -> dict:
    params = {
        "object_name": object_name,
        "script_name": script_name
    }
    if script_parameters:
        params["script_parameters"] = json.dumps(script_parameters, ensure_ascii=False)
    return {
        "action": "attach_script",
        "params": params
    }

@registry.register(
    name="modify_script_properties",
    description="修改指定物体上已挂载脚本的多个公共字段，传入属性字典。",
    parameters_description={
        "object_name": "目标物体名称",
        "script_name": "脚本名称(不带 .cs)",
        "new_script_parameters": "属性字典，键为字段名，值为新的字段值（支持 int、float、string、bool）"
    }
)
def tool_modify_script_properties(
        object_name: str,
        script_name: str,
        new_script_parameters: dict
) -> dict:
    params = {
        "object_name": object_name,
        "script_name": script_name,
        "new_script_parameters": json.dumps(new_script_parameters, ensure_ascii=False)  # 转为字符串发送
    }
    return {
        "action": "modify_script_properties",
        "params": params
    }

#  ==================== 预制体类 ====================
@registry.register(
    name="create_prefab",
    description="通过预制体来创建一个实例，并设置其空间信息（位置，旋转，大小），预制体名称和存放路径从项目规范中获取。",
    parameters_description={
        "object_name": "实例的自定义名称,可引用名称",
        "prefab_name": "现有的预制体名称（不带.prefab）",
        "path":"预制体所在的目录，例如 'Assets/Prefab/Enemy'（不要包含文件名）",
        "position": "位置坐标 [x,y,z]（可选，默认 [0,0,0]）",
        "localRotation": "局部旋转欧拉角 [x, y, z]（可选，默认 [0,0,0]）",
        "localScale": "缩放比例，格式为[x,y,z]（可选，默认 [1,1,1]）"
    }
)
def tool_create_prefab(
        object_name: str,
        prefab_name: str,
        path:str,
        position: list = [0, 0, 0],
        localRotation: list = [0, 0, 0],
        localScale: list = [1, 1, 1]
) -> dict:
    params = {
        "object_name": object_name,
        "prefab_name": prefab_name,
        "position": position
    }
    if path:
        params["path"] = path
    if localRotation:
        params["localRotation"] = localRotation
    if localScale:
        params["localScale"] = localScale
    return {
        "action": "create_prefab",
        "params": params
    }

@registry.register(
    name="echo",
    description="仅显示文本",
    parameters_description={
        "text":"文本",
    }
)
def tool_echo(
        text: str
) -> dict:
    return {
        "action": "echo",
        "params": {
            "text": text
        }
    }

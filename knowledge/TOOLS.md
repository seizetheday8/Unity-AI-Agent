# Unity Agent 工具集

## create_object
在 Unity 场景中创建一个基础几何体（无材质）,创建完会选中

**参数**:
```json
{
  "object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "物体名称"
  },
  "type": {
    "type": "<class 'str'>",
    "default": "Cube",
    "description": "几何体类型（Cube/Sphere/Capsule/Cylinder/Plane/Quad）"
  },
  "position": {
    "type": "<class 'list'>",
    "default": [
      0,
      0,
      0
    ],
    "description": "位置坐标，格式为[x,y,z]（可选，默认 [0,0,0]）"
  },
  "localRotation": {
    "type": "<class 'list'>",
    "default": [
      0,
      0,
      0
    ],
    "description": "局部旋转欧拉角 [x, y, z]（可选，默认 [0,0,0]）"
  },
  "localScale": {
    "type": "<class 'list'>",
    "default": [
      1,
      1,
      1
    ],
    "description": "缩放比例，格式为[x,y,z]（可选，默认 [1,1,1]）"
  }
}
```

## delete_object
删除指定物体（安全检查会阻止删除关键物体如 Main Camera）

**参数**:
```json
{
  "object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "要删除的物体名称"
  }
}
```

## modify_object
修改指定物体的属性（名字、位置、旋转、缩放），只需提供要修改的字段

**参数**:
```json
{
  "object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "要修改的原物体名称"
  },
  "new_object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "修改后的物体名称"
  },
  "position": {
    "type": "<class 'list'>",
    "default": null,
    "description": "新的位置坐标 [x, y, z]（可选）"
  },
  "localRotation": {
    "type": "<class 'list'>",
    "default": null,
    "description": "新的局部旋转欧拉角 [x, y, z]（可选）"
  },
  "localScale": {
    "type": "<class 'list'>",
    "default": null,
    "description": "新的局部缩放 [x, y, z]（可选）"
  }
}
```

## duplicate_object
复制指定物体,会完整保留原物体的所有组件、挂载的脚本以及脚本中的字段值（深拷贝）,并可设置新名称、位置、旋转、缩放（若未指定则与原物体相同）

**参数**:
```json
{
  "object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "要复制的物体名称"
  },
  "new_object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "新物体名称（可选）"
  },
  "position": {
    "type": "<class 'list'>",
    "default": null,
    "description": "新的位置坐标 [x, y, z]（可选）"
  },
  "localRotation": {
    "type": "<class 'list'>",
    "default": null,
    "description": "新的局部旋转欧拉角 [x, y, z]（可选）"
  },
  "localScale": {
    "type": "<class 'list'>",
    "default": null,
    "description": "新的局部缩放 [x, y, z]（可选）"
  }
}
```

## get_selected_object
获取当前在Unity场景中选中的物体名称（如果没有选中物体，返回空字符串）

**参数**:
```json
{}
```

## get_scene_objects
获取当前Unity场景中所有物体的名称列表（最多返回50个）

**参数**:
```json
{}
```

## create_material
仅创建一个材质，无其它操作

**参数**:
```json
{
  "material_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "材质名称"
  },
  "colorHex": {
    "type": "<class 'str'>",
    "default": "#FFFFFF",
    "description": "颜色十六进制值,如#FFFFFF"
  }
}
```

## set_material
为指定物体设置现有材质（材质必须已存在，否则会失败）

**参数**:
```json
{
  "object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "要设置材质的物体名称"
  },
  "material_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "材质名称（需已存在于项目中）"
  }
}
```

## attach_script
将脚本挂载到指定物体上，并可设置脚本的公共字段参数

**参数**:
```json
{
  "object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "目标物体名称"
  },
  "script_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "脚本名称（不带 .cs）"
  },
  "script_parameters": {
    "type": "<class 'dict'>",
    "default": null,
    "description": "脚本参数，字典形式，键为字段名，值为字段值（可选）"
  }
}
```

## modify_script_properties
修改指定物体上已挂载脚本的多个公共字段，传入属性字典。

**参数**:
```json
{
  "object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "目标物体名称"
  },
  "script_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "脚本名称(不带 .cs)"
  },
  "new_script_parameters": {
    "type": "<class 'dict'>",
    "default": null,
    "description": "属性字典，键为字段名，值为新的字段值（支持 int、float、string、bool）"
  }
}
```

## create_prefab
通过预制体来创建一个实例，并设置其空间信息（位置，旋转，大小），预制体名称和存放路径从项目规范中获取。

**参数**:
```json
{
  "object_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "实例的自定义名称,可引用名称"
  },
  "prefab_name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "现有的预制体名称（不带.prefab）"
  },
  "path": {
    "type": "<class 'str'>",
    "default": null,
    "description": "预制体所在的目录，例如 'Assets/Prefab/Enemy'（不要包含文件名）"
  },
  "position": {
    "type": "<class 'list'>",
    "default": [
      0,
      0,
      0
    ],
    "description": "位置坐标 [x,y,z]（可选，默认 [0,0,0]）"
  },
  "localRotation": {
    "type": "<class 'list'>",
    "default": [
      0,
      0,
      0
    ],
    "description": "局部旋转欧拉角 [x, y, z]（可选，默认 [0,0,0]）"
  },
  "localScale": {
    "type": "<class 'list'>",
    "default": [
      1,
      1,
      1
    ],
    "description": "缩放比例，格式为[x,y,z]（可选，默认 [1,1,1]）"
  }
}
```

## echo
仅显示文本

**参数**:
```json
{
  "text": {
    "type": "<class 'str'>",
    "default": null,
    "description": "文本"
  }
}
```


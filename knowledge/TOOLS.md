# Unity Agent 工具集

## create_object
在 Unity 场景中创建一个基础几何体（无材质）

**参数**:
```json
{
  "name": {
    "type": "<class 'str'>",
    "default": null,
    "description": "物体名称"
  },
  "type": {
    "type": "<class 'str'>",
    "default": "Cube",
    "description": "几何体类型（Cube/Sphere等）"
  },
  "position": {
    "type": "<class 'list'>",
    "default": [
      0,
      0,
      0
    ],
    "description": "位置坐标，格式为[x,y,z]"
  },
  "localScale": {
    "type": "<class 'list'>",
    "default": [
      1,
      1,
      1
    ],
    "description": "缩放比例，格式为[x,y,z]"
  }
}
```

## create_material_for_select
为选中的物体添加上创建的材质

**参数**:
```json
{
  "name": {
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

## create_material
仅创建一个材质，无其它操作

**参数**:
```json
{
  "name": {
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


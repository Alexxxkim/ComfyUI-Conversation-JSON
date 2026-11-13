# 在 ByteArtist 房间还原节点接口

本包是完整的 ComfyUI Custom Node，不是 WEP / Inline Python 脚本。不要只复制 `nodes.py`，也不要省略 `web/`。

## 安装

1. 在 BA 的 Git 仓库 Custom Node 下载入口填写 `https://github.com/Alexxxkim/ComfyUI-Conversation-JSON.git`。
2. 选择 `branch` 模式，分支填 `main`。需要固定版本时，改用发布后的完整 commit SHA。
3. 下载整个仓库并安装到目标房间的 ComfyUI 后端，避免多嵌套一层目录。
4. 按 BA 提供的操作重启或重新加载后端，再刷新房间网页。只刷新网页不会重新加载 Python 节点。
5. 在 `DM Canvas/Conversation` 分类中添加下列两个节点，或导入 `examples/conversation_json.workflow.json`。

```text
ComfyUI/custom_nodes/ComfyUI-Conversation-JSON/
├── __init__.py
├── nodes.py
├── conversation.py
├── web/conversation_input_labels.js
└── examples/conversation_json.workflow.json
```

## 应还原的接口

### Conversation JSON · 对话上下文转 JSON

- 左侧连接口：`conversation`，必填，`STRING`；`region`，可选，`STRING`。
- 节点内控件：`input_format`、`case_index`。这两个保留为控件，不强制变成外接接口。
- 右侧输出口：`json`、`image_order`、`warnings`，均为 `STRING`；`case_count` 为 `INT`。
- `conversation` 和 `region` 不应变成节点内文本框；`conversation` 标签不应空白。

```text
上下文 Text / String ──→ conversation
地区 Text / String   ──→ region
```

### Conversation Image Order · 对话图片排序

- 左侧连接口：`image_order` 为 `STRING`；`source_1` 到 `source_10` 为可选 `IMAGE`。
- 右侧输出口：`canvas_image_1` 到 `canvas_image_10`，均为 `IMAGE`。
- 按原始编号接源图，不按倒排后的位置接源图。只连接实际有图片的输出；空输出是 `None`。
- 示例工作流展示全部接口，但没有附带图片像素。排序节点只有接入实际图片、且输出连接到下游时才需要执行。

## 为什么不依赖本地手动转换

Python 定义使用 `STRING` 和 `forceInput: true` 声明文本连接口，避免 `STRING → *` 类型不匹配；`__init__.py` 注册两个节点并声明 `WEB_DIRECTORY`。前端扩展固定 `conversation` 标签，修复旧工作流遗留的文本控件关联，并保留已有文本、连线及旧版 `case_index` / `input_format`。

示例只包含虚构对话和地区文本，不包含真实用户历史、模型配置、API Key 或图片。

## 排查与验证范围

- 仍显示文本框：确认安装的是完整 Custom Node 仓库，而不是 Script / Inline Python；确认后端已重载，且加载了 `web/conversation_input_labels.js`。
- 标签空白：确认房间允许加载插件前端扩展，并刷新网页。
- 搜不到节点：确认后端成功导入根目录 `__init__.py`，且节点名是 `DMCanvasConversationJSONV2` / `DMCanvasConversationImageOrder`。
- 不要同时安装多个注册同名节点的旧副本；更新必须同时包含 Python 和 `web/`。

本版本已经在本地 ComfyUI 验证接口显示、文本执行和图片排序，并有 Python / JavaScript 回归测试。尚未在 BA 房间安装实测；如果平台忽略 `forceInput` 或禁止前端扩展，不能仅凭仓库上传保证界面完全一致。

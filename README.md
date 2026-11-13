# ComfyUI Conversation JSON

本地、无额外依赖的 ComfyUI 节点。新增独立节点类型，不覆盖旧版 Intent Input JSON 或风格选择器。

## 在 BA 房间还原

安装完整 Custom Node 仓库，保留根目录 Python 文件、`web/` 前端扩展和示例工作流。`conversation` / `region` 是带名称的左侧 `STRING` 连接口；`input_format` / `case_index` 是节点内控件。不要改成 Script / Inline Python，也不要只复制 `.py` 文件。安装与验收步骤见 [BYTEARTIST_INSTALL.md](BYTEARTIST_INSTALL.md)。BA 房间尚未实测，不将本地验证等同于 BA 验证。

## 节点

- `Conversation JSON · 对话上下文转 JSON`，分类 `DM Canvas/Conversation`。
- `Conversation Image Order · 对话图片排序`，同分类；用于实际图片接线与 JSON 标签保持一致。

`conversation` 是独立必填 STRING 输入口：将完整历史或简版对话粘贴到单独的多行文本节点，再把 STRING 输出连接到 `conversation`。`region` 是独立可选 STRING 输入口，格式 `[locale=en-AU]`；不连接时省略 `locale`。两个输入互不影响，最后一条消息必须是 user 的规则只针对 `conversation`。

接口固定显示 `conversation`。前端扩展会修复旧版文本框转接口后标签空白的问题，保留已有文本与接线；更新后重启 ComfyUI 并刷新页面即可生效。

`input_format` 支持 `auto`、`simple`、`full`。完整输入中遇到 `[1]` 消息编号重新开始，会识别为新的 case；`case_index` 从 1 开始选择，绝不合并不同会话。`case_count` 输出检测到的独立 case 总数，不是消息数或图片数。例如一次输入 100 条独立会话，`case_index=3` 只转换第 3 条，`case_count=100`。单条对话保持 `case_index=1`，不用连接 `case_count`。这两个字段不进入最终 JSON。`warnings` 输出不完整历史或人物占位符等提示。

## 简版输入

```text
user: [1][2] 生成一张合照
ai: [3]
user: [4][5] 让这两个人也加入之前的合照
```

- 最后一条消息是未得到答复的 user；此前消息进入 history，不重复当前请求。
- 图片支持 `[1]`、`[图1]`、`[图 1]`。编号是源图片身份，不是最终传输位置。同图可复用编号，最近一次出现决定其排序位置；实际传输去重。
- `ai: [3]` / `ai: [3][4]` 表示实际返回图片；`ai: failed` 表示失败；`ai: cancelled` 表示取消。兼容 `canceled` 拼写。
- 允许连续 user、连续 ai、只有图片的当前请求，以及非创作文字。用户文字不总结、不改写。
- 正文支持多行，直到下一个行首 `user:` / `ai:`。大小写和中文冒号兼容。
- 正文中如果一行真的以消息标记开头，写 `\user:` 或 `\ai:` 转义。普通正文中需要字面量 `[1]` 而不是图片时，写 `\[1]`。
- 不写 AI 套话、失败原因或 pending。`Thinking...` 占位消息会过滤。
- 地区仅从独立 `region` 输入读取，不从用户正文提取。

## 完整历史输入

```text
[1] 用户 · 2026-09-13 13:52:02
Create a sticker of someone dancing

[2] AI · 2026-09-13 13:52:03
Here's your sticker.[图1]

[3] 用户 · 2026-09-13 13:52:50
Make it a cat
```

完整记录中：有编号结果图片的 AI 记录保留为 succeeded；`[生成失败:...]` 统一为 failed，不输出原因；`Generation cancelled` / `Generation canceled` / `Đã hủy quá trình tạo` 统一为 cancelled。AI 正文不进入 JSON。缺少起始用户消息时保留已有片段并提示，不补造上下文。未识别的 AI 正文省略并给出 warning，不推断其生成状态。

仅有失败/取消结果、尚未追加下一条 user 的输入没有当前请求，会报错。源图片 0、含图片又声明失败/取消的 AI 记录、错误的地区格式同样会给出明确错误。

## 输出与图片映射

上面的简版例子按批次从 `[1,2] → [3] → [4,5]` 倒排为 `[4,5,3,1,2]`，批次内不反转。

`json` 输出：

```json
{
  "current_request": {
    "role": "user",
    "text": "[canvas_image_1][canvas_image_2] 让这两个人也加入之前的合照"
  },
  "history": [
    {
      "role": "user",
      "text": "[canvas_image_4][canvas_image_5] 生成一张合照"
    },
    {
      "role": "assistant",
      "generation_status": "succeeded",
      "image_ids": ["canvas_image_3"]
    }
  ],
  "locale": "en-AU"
}
```

`image_order` 输出 `[4, 5, 3, 1, 2]`。如果已有上游系统按此顺序传输图片，直接使用 JSON 即可。否则将 image_order 连接图片排序节点，原始 `[1]` 图片接 `source_1`，原始 `[2]` 接 `source_2`，以此类推；输出 `canvas_image_1` 接模型的第一路图片输入。

图片排序节点对应十路模型输入，保留每张图片自己的尺寸和张量，不拼接、不缩放、不重新生成图片。只连接实际有图片的前 N 路输出；后续空输出为 None，不应连接到需要真实图片的下游。JSON 转换节点本身不限制图片数量。

文字输入不能恢复图片像素；完整历史中的所有编号图片需要通过外部加载节点提供。`[提及用户]` 等匿名占位符也无法还原具体人物。

## 安装与测试

将整个目录放入 `ComfyUI/custom_nodes/`，重启 ComfyUI。示例工作流位于 `examples/conversation_json.workflow.json`，可拖入画布，已分别连接上下文和地区文本节点，并展示图片排序节点的十路接口。从旧版内置文本框升级时，重载新版示例或重新添加转换节点，再将原对话文本移到独立文本节点并连接 `conversation`。

```bash
python -m unittest discover -s tests -v
node --experimental-vm-modules --test tests/test_input_labels.mjs
```

用实际导出历史验证全部 case 时，将 `DMCANVAS_HISTORY_FIXTURE` 环境变量设为该文本文件路径。测试只在本地读取，不将用户聊天历史打包或上传。

将 `DMCANVAS_COMFYUI_TEST_URL` 设为本地 ComfyUI 地址，可验证真实节点注册、文本执行和十路图片排序；这些测试需要 ComfyUI 自带的 Pillow，不新增运行依赖。

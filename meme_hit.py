import json

from comfy_api.latest import ComfyExtension, io


OFF = "off · 不使用"
APPEND = "append · 补入库图"
REUSE = "reuse · 复用原图"
VISUAL = "视觉描述（必填）"
SOURCE = "原对话图号（必填）"
MATCHED = "命中的用户原话（选填）"


class MemeHit(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        visual = io.String.Input(
            VISUAL, multiline=True, default="",
            placeholder="视觉描述（必填）：梗图里最有辨识度的角色、动作或构图。",
            dynamic_prompts=False,
        )
        source = io.Int.Input(
            SOURCE, default=1, min=1,
            tooltip="原对话写 [图4] 就填 4，不是 V4 重排后的编号。",
        )
        matched = io.String.Input(
            MATCHED, optional=True, default="",
            placeholder="例如 tung tung tung sahur；仅凭图片命中时可留空。", dynamic_prompts=False,
        )
        return io.Schema(
            node_id="DMCanvasMemeHit", display_name="Meme Hit · 梗参考信息", category="DM Canvas",
            description="off：不使用；append：补库图；reuse：复用原图。仅输出 V4 参考信息，不传图片。",
            inputs=[io.DynamicCombo.Input("mode", display_name="参考方式", options=[
                io.DynamicCombo.Option(OFF, []),
                io.DynamicCombo.Option(APPEND, [visual, matched]),
                io.DynamicCombo.Option(REUSE, [visual, source, matched]),
            ])],
            outputs=[io.String.Output(display_name="Meme Hit")],
        )

    @classmethod
    def execute(cls, mode: dict) -> io.NodeOutput:
        selection = mode["mode"]
        if selection == OFF:
            return io.NodeOutput("")
        if selection not in (APPEND, REUSE):
            raise ValueError("参考方式请选择 off、append 或 reuse。")
        visual = mode.get(VISUAL, "").strip()
        if not visual:
            raise ValueError("请填写视觉描述，或将参考方式切回 off。")
        hit = {"mode": "append" if selection == APPEND else "reuse", "visual_core": visual}
        if selection == REUSE:
            source = mode.get(SOURCE)
            if type(source) is not int or source < 1:
                raise ValueError("原对话图号请填写正整数，如 [图4] 填 4。")
            hit["source_image"] = source
        matched = (mode.get(MATCHED) or "").strip()
        if matched:
            hit["matched_text"] = matched
        return io.NodeOutput(json.dumps(hit, ensure_ascii=False, indent=2))


class MemeHitExtension(ComfyExtension):
    async def get_node_list(self):
        return [MemeHit]


async def comfy_entrypoint():
    return MemeHitExtension()

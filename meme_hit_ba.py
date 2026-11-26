import json

from .conversation_json_v4 import read_hit


class MemeHitBA:
    CATEGORY = "DM Canvas/Conversation"
    FUNCTION = "build"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("Meme Hit",)
    DESCRIPTION = "固定表单，不需要 DynamicCombo。仅在 reuse 时读取图号；off 时忽略所有字段。输出接 V4 的 Meme 01 或 Meme 02。"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "mode": (["off · 不使用", "append · 补入库图", "reuse · 复用原图"], {"display_name": "参考方式"}),
        }, "optional": {
            "visual_core": ("STRING", {"display_name": "视觉描述（启用时必填）", "multiline": True, "default": "", "dynamicPrompts": False}),
            "source_image": ("INT", {"display_name": "原对话图号（仅复用）", "default": 1, "min": 1, "tooltip": "[图4] 填 4。补库图时忽略，不用清空。"}),
            "matched_text": ("STRING", {"display_name": "命中的用户原话（选填）", "default": "", "dynamicPrompts": False}),
        }}

    def build(self, mode, visual_core="", source_image=None, matched_text=""):
        selection = mode.partition(" · ")[0]
        fields = {"mode": selection, "visual_core": visual_core, "matched_text": matched_text}
        if selection == "reuse":
            fields["source_image"] = source_image
        hit = read_hit(fields, "Meme Hit")
        return (json.dumps(hit, ensure_ascii=False, indent=2) if hit else "",)

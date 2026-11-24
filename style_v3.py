import json

from .nodes import ConversationJSONPrefixV2


class ConversationJSONV3(ConversationJSONPrefixV2):
    DESCRIPTION = "在 V2 输出的顶层按需添加 style 对象；不改变用户指令或历史。风格名称留空时，四路输出与 V2 完全相同。"

    @classmethod
    def INPUT_TYPES(cls):
        inputs = super().INPUT_TYPES()
        inputs["optional"].update({
            "style_name": ("STRING", {"forceInput": True, "tooltip": "风格名称。未连接或只有空白时不输出 style。"}),
            "style_prompt": ("STRING", {"forceInput": True, "tooltip": "风格规则，支持多行。仅在有风格名称时使用。"}),
        })
        return inputs

    def convert(self, conversation, input_format="auto", case_index=1, region="", style_name="", style_prompt=""):
        result = super().convert(conversation, input_format, case_index, region)
        name = (style_name or "").strip()
        if not name:
            return result
        payload = json.loads(result[0])
        payload["style"] = {"name": name, "prompt": style_prompt if (style_prompt or "").strip() else ""}
        return (json.dumps(payload, ensure_ascii=False, indent=2), *result[1:])

from .conversation_json_v4 import ConversationJSONV3, run


class ConversationJSONV4(ConversationJSONV3):
    DESCRIPTION = "原始对话转 VLM JSON。可接零到两个 Meme Hit；Attachment Plan 给出原图与库图的最终顺序，不传图片。"
    RETURN_TYPES = (*ConversationJSONV3.RETURN_TYPES, "STRING")
    RETURN_NAMES = (*ConversationJSONV3.RETURN_NAMES, "attachment_plan")

    @classmethod
    def INPUT_TYPES(cls):
        inputs = super().INPUT_TYPES()
        inputs["required"]["input_format"] = (["auto", "simple", "full", "wep"], {"default": "auto"})
        for port, label in (("meme_01", "Meme 01"), ("meme_02", "Meme 02")):
            inputs["optional"][port] = ("STRING", {
                "forceInput": True, "display_name": label, "tooltip": "接 Meme Hit 的文本输出；未连接或 off 时跳过。",
            })
        return inputs

    def convert(self, conversation, input_format="auto", case_index=1, region="", style_name="", style_prompt="",
                meme_01="", meme_02=""):
        result = run({
            "conversation": conversation, "region": region, "style_name": style_name, "style_prompt": style_prompt,
            "settings": {"input_format": input_format, "case_index": case_index},
            "meme_01": meme_01, "meme_02": meme_02,
        })
        return result["json"], result["image_order"], result["warnings"], int(result["case_count"]), result["attachment_plan"]


NODE_CLASS_MAPPINGS = {"DMCanvasConversationJSONV4": ConversationJSONV4}
NODE_DISPLAY_NAME_MAPPINGS = {"DMCanvasConversationJSONV4": "Conversation JSON V4 · 对话与梗参考"}

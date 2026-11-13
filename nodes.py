import json

from .conversation import format_conversation, parse_image_order


EXAMPLE = """user: [1][2] 生成一张合照
ai: [3]
user: [4][5] 让这两个人也加入之前的合照"""
CATEGORY = "DM Canvas/Conversation"


class ConversationJSON:
    CATEGORY = CATEGORY
    FUNCTION = "convert"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("json", "image_order", "warnings", "case_count")
    DESCRIPTION = "完整历史或 user:/ai: 简版转为当前请求和历史 JSON；图片批次倒排、批次内顺序不变。conversation 和 region 均为独立输入。"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "conversation": ("STRING", {
                    "forceInput": True, "display_name": "conversation",
                    "multiline": True, "default": EXAMPLE, "dynamicPrompts": False,
                    "tooltip": "单独连接上下文文本，支持完整历史或 user:/ai: 简版；最后一条消息是当前用户请求。",
                }),
                "input_format": (["auto", "simple", "full"], {"default": "auto"}),
                "case_index": ("INT", {"default": 1, "min": 1, "tooltip": "完整文本包含多条 case 时，选择第几条；从 1 开始。"}),
            },
            "optional": {
                "region": ("STRING", {"forceInput": True, "tooltip": "单独连接地区文本，如 [locale=en-AU]；不连接则不输出 locale。"}),
            },
        }

    def convert(self, conversation, input_format="auto", case_index=1, region=""):
        payload, order, warnings, count = format_conversation(conversation, region, input_format, case_index)
        return (json.dumps(payload, ensure_ascii=False, indent=2),
                json.dumps(order), "\n".join(warnings), count)


class ConversationImageOrder:
    CATEGORY = CATEGORY
    FUNCTION = "reorder"
    RETURN_TYPES = ("IMAGE",) * 10
    RETURN_NAMES = tuple(f"canvas_image_{index}" for index in range(1, 11))
    DESCRIPTION = "源图 [N] 接 source_N，连接转换节点的 image_order 后，输出与 JSON 标签一致的十路图片。保留图片尺寸，不拼接批次。"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"image_order": ("STRING", {"forceInput": True})},
            "optional": {
                f"source_{index}": ("IMAGE", {"tooltip": f"原始编号 [{index}] 的图片，不是倒排后的第 {index} 张。"})
                for index in range(1, 11)
            },
        }

    def reorder(self, image_order, **sources):
        order = parse_image_order(image_order)
        if len(order) > 10:
            raise ValueError("此图片排序节点对应十路模型输入，不能路由超过 10 张图片；文本 JSON 转换不限制图片数量。")
        result = []
        for number in order:
            image = sources.get(f"source_{number}")
            if image is None:
                raise ValueError(f"缺少源图片 [{number}]；请连接 source_{number}，不要按倒排位置连接源图。")
            result.append(image)
        return tuple(result + [None] * (10 - len(result)))


NODE_CLASS_MAPPINGS = {
    "DMCanvasConversationJSONV2": ConversationJSON,
    "DMCanvasConversationImageOrder": ConversationImageOrder,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "DMCanvasConversationJSONV2": "Conversation JSON · 对话上下文转 JSON",
    "DMCanvasConversationImageOrder": "Conversation Image Order · 对话图片排序",
}

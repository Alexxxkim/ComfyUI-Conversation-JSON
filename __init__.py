from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .reference_v4 import ConversationJSONV4
from .style_v3 import ConversationJSONV3


NODE_CLASS_MAPPINGS = {
    **NODE_CLASS_MAPPINGS,
    "DMCanvasConversationJSONV3": ConversationJSONV3,
    "DMCanvasConversationJSONV4": ConversationJSONV4,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    **NODE_DISPLAY_NAME_MAPPINGS,
    "DMCanvasConversationJSONV3": "Conversation JSON V3 · 对话上下文转 JSON（可选风格）",
    "DMCanvasConversationJSONV4": "Conversation JSON V4 · 对话与梗参考",
}

try:
    from comfy_api.latest import io
except ImportError as error:
    if error.name not in {"comfy_api", "comfy_api.latest"}:
        raise
    io = None

if hasattr(io, "DynamicCombo"):
    from .meme_hit import MemeHit

    NODE_CLASS_MAPPINGS["DMCanvasMemeHit"] = MemeHit
    NODE_DISPLAY_NAME_MAPPINGS["DMCanvasMemeHit"] = "Meme Hit · 梗参考信息"

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

import json
import re


FULL_HEADER = re.compile(
    r"^[ \t]*\[([0-9]+)\][ \t]*(用户|AI)[ \t]*·[^\r\n]*(?:\r?\n|$)",
    re.MULTILINE,
)


SIMPLE_HEADER = re.compile(r"^[ \t]*(user|ai|assistant)[ \t]*[:：][ \t]*(.*)$", re.IGNORECASE)


ESCAPED_HEADER = re.compile(r"^([ \t]*)\\((?:user|ai|assistant)[ \t]*[:：].*)$", re.IGNORECASE)


IMAGE_REFERENCE = re.compile(r"(?<!\\)\[(?:图[ \t]*)?([0-9]+)\]")


REGION = re.compile(r"\[[ \t]*locale[ \t]*=[ \t]*([^\s\[\]=]+)[ \t]*\]", re.IGNORECASE)


FAILURE = re.compile(r"\[生成失败(?::[^\]]*)?\]")


CANCELLATION = re.compile(r"Generation cancel(?:l)?ed", re.IGNORECASE)


def image_numbers(text):
    numbers = list(dict.fromkeys(int(match.group(1)) for match in IMAGE_REFERENCE.finditer(text)))
    if 0 in numbers:
        raise ValueError("图片编号必须是正整数，例如 [1] 或 [图1]。")
    return numbers


def parse_region(region):
    if region is None or region == "":
        return None
    if not isinstance(region, str):
        raise ValueError("region 必须是文本，格式为 [locale=en-AU]。")
    if not region.strip():
        return None
    match = REGION.fullmatch(region.strip())
    if not match:
        raise ValueError("region 请单独输入 [locale=en-AU]，locale 不能为空。")
    return match.group(1)


def parse_simple(text):
    messages = []
    for line in text.splitlines():
        escaped = ESCAPED_HEADER.fullmatch(line)
        header = None if escaped else SIMPLE_HEADER.fullmatch(line)
        if header:
            role, body = header.groups()
            messages.append({"role": "user" if role.lower() == "user" else "assistant", "lines": [body]})
        elif messages:
            messages[-1]["lines"].append("".join(escaped.groups()) if escaped else line)
        elif line.strip():
            raise ValueError("简化输入请以 user: 开始，图片写 [1]，失败写 ai: failed，取消写 ai: cancelled。")
    return [[{"role": message["role"], "text": "\n".join(message["lines"]).strip("\r\n")}
             for message in messages]]


def parse_full(text):
    headers = list(FULL_HEADER.finditer(text))
    if not headers or text[:headers[0].start()].strip():
        raise ValueError("完整历史格式须为 [1] 用户 · 日期时间，下一行是消息正文。")
    cases = []
    for index, header in enumerate(headers):
        if not cases or header.group(1) == "1":
            cases.append([])
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        cases[-1].append({
            "role": "user" if header.group(2) == "用户" else "assistant",
            "text": text[header.end():end].strip("\r\n"),
        })
    return cases


def normalize_messages(messages, strict):
    normalized = []
    warnings = []
    for index, message in enumerate(messages, 1):
        body = message["text"]
        numbers = image_numbers(body)
        if message["role"] == "user":
            normalized.append({"role": "user", "text": body, "images": numbers})
            continue
        clean_body = body.strip()
        lowered = clean_body.lower()
        if FAILURE.search(body) or lowered == "failed":
            status = "failed"
        elif (lowered in ("cancelled", "canceled") or CANCELLATION.search(body)
              or clean_body == "Đã hủy quá trình tạo"):
            status = "cancelled"
        elif numbers:
            if strict and IMAGE_REFERENCE.sub("", clean_body).strip():
                raise ValueError(f"第 {index} 条 ai 成功消息只写图片标签；其他正文请省略。")
            status = "succeeded"
        elif lowered in ("thinking...", "thinking…"):
            continue
        else:
            if strict:
                raise ValueError(f"第 {index} 条 ai 消息须为图片标签、failed 或 cancelled；不支持空消息或其他正文。")
            warnings.append(f"第 {index} 条 AI 记录没有图片或已知结果状态，已省略；未推断生成状态。")
            continue
        if numbers and status != "succeeded":
            raise ValueError(f"第 {index} 条 AI 记录同时含图片和 {status}，请拆分成功图片与失败/取消事件。")
        normalized.append({"role": "assistant", "generation_status": status, "images": numbers})
    if not normalized or normalized[-1]["role"] != "user":
        raise ValueError("最后一条对话消息必须是尚未得到答复的 user 请求；请在 AI 结果之后追加本次用户内容。")
    if not normalized[-1]["text"].strip():
        raise ValueError("当前 user 请求不能为空；只有图片时可以写 user: [1]。")
    if normalized[0]["role"] == "assistant":
        warnings.append("历史以 AI 记录开头，可能缺少起始用户消息；已保留已有记录，未补造上下文。")
    if any(message["role"] == "user" and "[提及用户]" in message["text"] for message in normalized):
        warnings.append("存在 [提及用户] 占位符；具体人物身份未提供，不能从该占位符推断对应图片。")
    return normalized, warnings


def format_conversation(conversation, region="", input_format="auto", case_index=1):
    if not isinstance(conversation, str):
        raise ValueError("conversation 必须是文本。")
    text = conversation.lstrip("\ufeff")
    if input_format not in ("auto", "simple", "full"):
        raise ValueError("input_format 必须为 auto、simple 或 full。")
    if isinstance(case_index, bool) or not isinstance(case_index, int) or case_index < 1:
        raise ValueError("case_index 必须是从 1 开始的整数。")
    mode = input_format
    if mode == "auto":
        mode = "full" if FULL_HEADER.match(text.lstrip()) else "simple"
    cases = parse_full(text) if mode == "full" else parse_simple(text)
    if case_index > len(cases):
        raise ValueError(f"只检测到 {len(cases)} 条 case，无法选择第 {case_index} 条。")
    messages, warnings = normalize_messages(cases[case_index - 1], strict=mode == "simple")
    order = []
    seen = set()
    for message in reversed(messages):
        for number in message["images"]:
            if number not in seen:
                order.append(number)
                seen.add(number)
    mapping = {number: f"canvas_image_{index}" for index, number in enumerate(order, 1)}

    def replace_images(body):
        replaced = IMAGE_REFERENCE.sub(lambda match: f"[{mapping[int(match.group(1))]}]", body)
        return re.sub(r"\\(?=\[(?:图[ \t]*)?[0-9]+\])", "", replaced)

    history = []
    for message in messages[:-1]:
        if message["role"] == "user":
            history.append({"role": "user", "text": replace_images(message["text"])})
        else:
            entry = {"role": "assistant", "generation_status": message["generation_status"]}
            if message["generation_status"] == "succeeded":
                entry["image_ids"] = [mapping[number] for number in message["images"]]
            history.append(entry)
    payload = {
        "current_request": {"role": "user", "text": replace_images(messages[-1]["text"])},
        "history": history,
    }
    locale = parse_region(region)
    if locale is not None:
        payload["locale"] = locale
    if len(cases) > 1:
        warnings.insert(0, f"检测到 {len(cases)} 条独立 case；当前选择第 {case_index} 条，未合并不同会话。")
    return payload, order, warnings, len(cases)


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


class ConversationJSONPrefixV2(ConversationJSON):
    DESCRIPTION = "V2：保留原版转换规则；从当前请求及历史中每条用户消息的开头移除 Create a sticker of / Remix，并在该消息中添加 prefix：R1 / R2。大小写须完全匹配，不要求前缀后有空格。"

    def convert(self, conversation, input_format="auto", case_index=1, region=""):
        result = super().convert(conversation, input_format, case_index, region)
        payload = json.loads(result[0])
        prefix_changed = False
        for message in [payload["current_request"], *payload["history"]]:
            if message["role"] != "user":
                continue
            for prefix_text, prefix_code in (("Create a sticker of", "R1"), ("Remix", "R2")):
                if message["text"].startswith(prefix_text):
                    message["text"] = message["text"][len(prefix_text):].lstrip()
                    message["prefix"] = prefix_code
                    prefix_changed = True
                    break
        if prefix_changed:
            return (json.dumps(payload, ensure_ascii=False, indent=2), *result[1:])
        return result


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


import sys

try:
    from workflow.decorators import input_slot, output_slot, script_meta
except ImportError:
    def passthrough_decorator(*args, **kwargs):
        return lambda function: function

    input_slot = output_slot = script_meta = passthrough_decorator


INPUT_FORMAT = "auto"
CASE_INDEX = 1
WEP_HEADER = re.compile(r"[ \t]*(user|ai|assistant)[:：][ \t]*(\d+(?:[ \t]*[,，][ \t]*\d+)*)?[ \t]*", re.I)
WEP_STATUS = re.compile(r"[ \t]*status[:：][ \t]*(cancelled|canceled|failed)[ \t]*", re.I)


def read_case_index(value):
    if value is None:
        return CASE_INDEX
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return CASE_INDEX
        if re.fullmatch(r"[0-9]+", value):
            value = int(value)
    if type(value) is not int or value < 1:
        raise ValueError("case_index 必须是从 1 开始的整数，例如 2。")
    return value


def legacy_messages(text):
    messages = []
    for line in text.lstrip("\ufeff").splitlines():
        header = WEP_HEADER.fullmatch(line)
        if header:
            role, numbers = header.groups()
            ids = [int(number) for number in re.split("[,，]", numbers)] if numbers else []
            messages.append((role.lower(), ids, []))
        elif SIMPLE_HEADER.match(line) or (not messages and line.strip()):
            return []
        elif messages:
            messages[-1][2].append(line)
    return messages


def has_legacy_markers(messages):
    for role, numbers, lines in messages:
        if role != "user" and numbers:
            return True
        if any(WEP_STATUS.fullmatch(line) for line in lines):
            return True
        if numbers and any(int(match.group(1)) in numbers for line in lines for match in IMAGE_REFERENCE.finditer(line)):
            return True
    return False


def convert_legacy_headers(messages):
    result = []
    for role, numbers, lines in messages:
        if any(number < 1 for number in numbers):
            raise ValueError("旧格式标题中的图片编号必须为正整数。")
        body = "\n".join(lines).strip("\r\n")
        if role == "user":
            statuses = [match.group(1).lower() for line in lines if (match := WEP_STATUS.fullmatch(line))]
            if len(statuses) > 1:
                raise ValueError("同一条历史用户请求不能有多个 status。")
            body = "\n".join(line for line in lines if not WEP_STATUS.fullmatch(line)).strip("\r\n")
            present = set(image_numbers(body))
            missing = "".join(f"[图{number}]" for number in dict.fromkeys(numbers) if number not in present)
            if missing:
                body = body + (" " if body and not body[-1].isspace() else "") + missing
            result.append("user: " + body)
            if statuses:
                result.append("ai: " + statuses[0])
        elif numbers:
            if WEP_STATUS.fullmatch(body) or body.strip().lower() in {"cancelled", "canceled", "failed"}:
                raise ValueError("同一条 AI 记录不能既有返图又标为失败或取消。")
            result.append("ai: " + "".join(f"[图{number}]" for number in numbers))
        elif body:
            result.append("ai: " + body)
    return "\n".join(result)


def convert_inputs(inputs):
    conversation = inputs.get("conversation")
    if conversation is None or (isinstance(conversation, str) and not conversation.strip()):
        return {"json": "", "image_order": "[]", "warnings": "", "case_count": "0"}
    mode = inputs.get("input_format")
    if isinstance(mode, str):
        mode = mode.strip().lower() or INPUT_FORMAT
    elif mode is None:
        mode = INPUT_FORMAT
    if mode not in ("auto", "simple", "full", "wep"):
        raise ValueError("input_format 必须为 auto、simple、full 或 wep。")
    case_index = read_case_index(inputs.get("case_index"))
    if isinstance(conversation, str) and mode in ("auto", "wep"):
        messages = legacy_messages(conversation)
        if mode == "wep" and not messages:
            raise ValueError("旧 WEP 格式应使用 user: 1,2 或 ai: 3 等角色标题。")
        if mode == "wep" or has_legacy_markers(messages):
            conversation = convert_legacy_headers(messages)
            mode = "simple"
    payload, order, warnings, count = ConversationJSONV3().convert(
        conversation, input_format=mode, case_index=case_index,
        region=inputs.get("region", ""), style_name=inputs.get("style_name", ""),
        style_prompt=inputs.get("style_prompt", ""),
    )
    return {"json": payload, "image_order": order, "warnings": warnings, "case_count": str(count)}


def run_cli(entrypoint):
    request = sys.stdin.read()
    print(json.dumps(entrypoint(json.loads(request) if request.strip() else {}), ensure_ascii=False))


def convert_v3(inputs):
    settings = inputs.get("settings")
    if settings is None or (isinstance(settings, str) and not settings.strip()):
        settings = {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except json.JSONDecodeError as error:
            raise ValueError('Settings 请填写 JSON 对象，例如 {"case_index": 2}。') from error
    if not isinstance(settings, dict) or settings.keys() - {"case_index", "input_format"}:
        raise ValueError("Settings 必须是 JSON 对象，且只支持 case_index 和 input_format。")
    if "case_index" in settings and (type(settings["case_index"]) is not int or settings["case_index"] < 1):
        raise ValueError("Settings 的 case_index 必须是从 1 开始的整数。")
    if "input_format" in settings and settings["input_format"] not in ("auto", "full", "simple", "wep"):
        raise ValueError("Settings 的 input_format 必须为 auto、full、simple 或 wep。")
    return convert_inputs({**inputs, "case_index": settings.get("case_index"), "input_format": settings.get("input_format")})


def read_hit(value, label):
    if value is None or isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"{label} 需要一个 Meme Hit JSON 对象。") from error
    fields = {"mode", "source_image", "visual_core", "name", "matched_text"}
    if not isinstance(value, dict) or value.keys() - fields:
        raise ValueError(f"{label} 必须是只含 Meme Hit 字段的对象。")
    if not value or value.get("mode") == "off":
        return None
    mode = value.get("mode")
    if mode not in ("reuse", "append"):
        raise ValueError(f"{label} 的 mode 请选择 off、reuse 或 append。")
    hit = {"mode": mode}
    for field in ("visual_core", "name", "matched_text"):
        text = value.get(field, "")
        if not isinstance(text, str):
            raise ValueError(f"{label} 的 {field} 必须是文本。")
        if text.strip():
            hit[field] = text.strip()
    if "visual_core" not in hit:
        raise ValueError(f"{label} 已启用，请填写视觉描述 visual_core，或切回 off。")
    source = value.get("source_image", "")
    if mode == "reuse":
        match = re.fullmatch(r"(?:([0-9]+)|\[(?:图[ \t]*)?([0-9]+)\])", str(source).strip())
        if not match or int(match.group(1) or match.group(2)) < 1:
            raise ValueError(f"{label} 的 source_image 请填原对话中的图号，如 4 或 [图4]，不要填 canvas_image_N。")
        hit["source_image"] = int(match.group(1) or match.group(2))
    elif source is not None and str(source).strip():
        raise ValueError(f"{label} 补库图时请留空 source_image；新图由 V4 编号。")
    return hit


@script_meta(display="Conversation JSON V4 · Meme References", settings={
    "type": "object",
    "properties": {
        "case_index": {"type": "integer", "title": "Case Index", "minimum": 1, "default": 1},
        "input_format": {"type": "string", "title": "Input Format", "enum": ["auto", "full", "simple", "wep"], "default": "auto"},
    },
})
@input_slot(index=0, label="Conversation", name="conversation", value_type="string")
@input_slot(index=1, label="Region", name="region", value_type="string")
@input_slot(index=2, label="Style Name", name="style_name", value_type="string")
@input_slot(index=3, label="Style Prompt", name="style_prompt", value_type="string")
@input_slot(index=4, label="Settings", name="settings", value_type="string")
@input_slot(index=5, label="Meme 01", name="meme_01", value_type="string")
@input_slot(index=6, label="Meme 02", name="meme_02", value_type="string")
@output_slot(index=0, label="JSON", name="json", value_type="string")
@output_slot(index=1, label="Image Order", name="image_order", value_type="string")
@output_slot(index=2, label="Warnings", name="warnings", value_type="string")
@output_slot(index=3, label="Case Count", name="case_count", value_type="string")
@output_slot(index=4, label="Attachment Plan", name="attachment_plan", value_type="string")
def run(inputs):
    result = convert_v3(inputs)
    original_order = json.loads(result["image_order"])
    originals = {number: f"canvas_image_{index}" for index, number in enumerate(original_order, 1)}
    plan = [{"image_ref": ref, "source_image": number} for number, ref in originals.items()]
    if result["json"]:
        refs = []
        appended = []
        for port in ("meme_01", "meme_02"):
            hit = read_hit(inputs.get(port), port)
            if not hit:
                continue
            if hit["mode"] == "reuse":
                number = hit["source_image"]
                if number not in originals:
                    raise ValueError(f"{port} 要复用的 [图{number}] 不在所选 case 的对话中。")
                ref = originals[number]
            else:
                ref = f"canvas_image_{len(plan) + 1}"
                plan.append({"image_ref": ref, "reference_from": port})
                appended.append(f"[{ref}]")
            entry = {"image_ref": ref, "visual_core": hit["visual_core"]}
            if "matched_text" in hit:
                entry["matched_text"] = hit["matched_text"]
            refs.append(entry)
        if refs:
            payload = json.loads(result["json"])
            if appended:
                payload["current_request"]["text"] += "\n\nRetrieved meme reference: " + " ".join(appended)
            payload["meme_refs"] = refs
            result["json"] = json.dumps(payload, ensure_ascii=False, indent=2)
    result["attachment_plan"] = json.dumps(plan, ensure_ascii=False)
    return result


if __name__ == "__main__":
    run_cli(run)

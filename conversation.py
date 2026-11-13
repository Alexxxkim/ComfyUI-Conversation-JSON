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


def parse_image_order(image_order):
    if not isinstance(image_order, str):
        raise ValueError("image_order 必须连接 JSON 转换节点的同名输出。")
    try:
        order = json.loads(image_order)
    except json.JSONDecodeError as error:
        raise ValueError("image_order 须为 JSON 数字数组，例如 [4, 5, 3, 1, 2]。") from error
    if not isinstance(order, list) or any(type(number) is not int or number < 1 for number in order):
        raise ValueError("image_order 须为正整数数组，例如 [4, 5, 3, 1, 2]。")
    if len(set(order)) != len(order):
        raise ValueError("image_order 不得包含重复图片编号。")
    return order

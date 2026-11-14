import io
import json
import os
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from test_prefix_v2 import EXAMPLES, HISTORY_CASE, HISTORY_PAYLOAD


SERVER_URL = os.environ.get("DMCANVAS_COMFYUI_TEST_URL", "").rstrip("/")


def request_json(path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(f"{SERVER_URL}{path}", data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


@unittest.skipUnless(SERVER_URL, "Set DMCANVAS_COMFYUI_TEST_URL to a running ComfyUI server.")
class ServerTests(unittest.TestCase):
    def execute(self, prompt):
        try:
            queued = request_json("/prompt", {"prompt": prompt})
        except HTTPError as error:
            self.fail(error.read().decode())
        prompt_id = queued["prompt_id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            history = request_json(f"/history/{prompt_id}")
            if prompt_id in history:
                return history[prompt_id]
            time.sleep(0.05)
        self.fail("Local test prompt did not finish within 30 seconds.")

    def converter_prompt(self, text, region=None, converter_type="DMCanvasConversationJSONV2"):
        prompt = {
            "1": {"class_type": converter_type, "inputs": {
                "conversation": ["5", 0], "input_format": "auto", "case_index": 1,
            }},
            "2": {"class_type": "PreviewAny", "inputs": {"source": ["1", 0]}},
            "3": {"class_type": "PreviewAny", "inputs": {"source": ["1", 1]}},
            "5": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": text}},
        }
        if region is not None:
            prompt["4"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": region}}
            prompt["1"]["inputs"]["region"] = ["4", 0]
        return prompt

    def test_registered_schema_and_separate_text_sockets(self):
        schemas = request_json("/object_info")
        converter = schemas["DMCanvasConversationJSONV2"]
        self.assertEqual(converter["output"], ["STRING", "STRING", "STRING", "INT"])
        self.assertTrue(converter["input"]["required"]["conversation"][1]["forceInput"])
        self.assertEqual(converter["input"]["required"]["conversation"][1]["display_name"], "conversation")
        self.assertEqual(converter["input"]["optional"]["region"], ["STRING", {
            "forceInput": True,
            "tooltip": "单独连接地区文本，如 [locale=en-AU]；不连接则不输出 locale。",
        }])
        self.assertEqual(schemas["DMCanvasConversationImageOrder"]["output"], ["IMAGE"] * 10)

    def test_v2_has_the_same_schema_and_a_distinct_display_name(self):
        schemas = request_json("/object_info")
        original = schemas["DMCanvasConversationJSONV2"]
        updated = schemas["DMCanvasConversationJSONPrefixV2"]
        for key in ("input", "input_order", "output", "output_name", "category"):
            self.assertEqual(updated[key], original[key])
        self.assertEqual(original["display_name"], "Conversation JSON · 对话上下文转 JSON")
        self.assertEqual(updated["display_name"], "Conversation JSON V2 · 对话上下文转 JSON（前缀识别）")

    def test_v2_all_twelve_user_examples_run_on_the_server(self):
        for index, (source, text, prefix, order) in enumerate(EXAMPLES, 1):
            with self.subTest(example=index):
                result = self.execute(self.converter_prompt(
                    f"user: {source}", converter_type="DMCanvasConversationJSONPrefixV2"
                ))
                self.assertEqual(result["status"]["status_str"], "success", result["status"])
                current_request = {"role": "user", "text": text}
                if prefix is not None:
                    current_request["prefix"] = prefix
                self.assertEqual(json.loads(result["outputs"]["2"]["text"][0]), {
                    "current_request": current_request, "history": [],
                })
                self.assertEqual(json.loads(result["outputs"]["3"]["text"][0]), order)

    def test_original_node_still_preserves_prefixes_on_the_server(self):
        result = self.execute(self.converter_prompt("user: Create a sticker of a cat"))
        self.assertEqual(result["status"]["status_str"], "success", result["status"])
        self.assertEqual(json.loads(result["outputs"]["2"]["text"][0]), {
            "current_request": {"role": "user", "text": "Create a sticker of a cat"}, "history": [],
        })

    def test_v2_processes_user_provided_history_on_the_server(self):
        result = self.execute(self.converter_prompt(
            HISTORY_CASE, converter_type="DMCanvasConversationJSONPrefixV2"
        ))
        self.assertEqual(result["status"]["status_str"], "success", result["status"])
        self.assertEqual(json.loads(result["outputs"]["2"]["text"][0]), HISTORY_PAYLOAD)
        self.assertEqual(json.loads(result["outputs"]["3"]["text"][0]), [2, 1])

    def test_simple_case_runs_with_external_conversation_and_region(self):
        result = self.execute(self.converter_prompt(
            "user: [1][2] 合照\nai: [3]\nuser: [4][5] 加入合照", "[locale=en-AU]"
        ))
        self.assertEqual(result["status"]["status_str"], "success", result["status"])
        payload = json.loads(result["outputs"]["2"]["text"][0])
        self.assertEqual(payload["locale"], "en-AU")
        self.assertEqual(payload["current_request"]["text"], "[canvas_image_1][canvas_image_2] 加入合照")
        self.assertEqual(json.loads(result["outputs"]["3"]["text"][0]), [4, 5, 3, 1, 2])

    def test_full_case_failure_and_cancellation_run_without_extra_fields(self):
        text = (
            "[1] 用户 · 2026-09-13 13:52:02\n[图1] 改图\n"
            "[2] AI · 2026-09-13 13:52:03\nError[生成失败:moderation]\n"
            "[3] 用户 · 2026-09-13 13:52:04\n再试\n"
            "[4] AI · 2026-09-13 13:52:05\nGeneration cancelled\n"
            "[5] 用户 · 2026-09-13 13:52:06\n为什么不行？"
        )
        result = self.execute(self.converter_prompt(text))
        self.assertEqual(result["status"]["status_str"], "success", result["status"])
        payload = json.loads(result["outputs"]["2"]["text"][0])
        self.assertEqual(payload["history"][1], {"role": "assistant", "generation_status": "failed"})
        self.assertEqual(payload["history"][3], {"role": "assistant", "generation_status": "cancelled"})
        self.assertEqual(payload["current_request"], {"role": "user", "text": "为什么不行？"})
        self.assertNotIn("locale", payload)

    def test_actual_image_router_preserves_pixels_dimensions_and_order(self):
        from PIL import Image

        prompt = {
            "1": {"class_type": "DMCanvasConversationImageOrder", "inputs": {"image_order": "[4, 5, 3, 1, 2]"}},
        }
        for number in range(1, 6):
            source_id = str(10 + number)
            prompt[source_id] = {"class_type": "EmptyImage", "inputs": {
                "width": 64 + number * 8, "height": 64, "batch_size": 1, "color": number * 0x110000,
            }}
            prompt["1"]["inputs"][f"source_{number}"] = [source_id, 0]
        for index in range(5):
            prompt[str(20 + index)] = {"class_type": "PreviewImage", "inputs": {"images": ["1", index]}}
        result = self.execute(prompt)
        self.assertEqual(result["status"]["status_str"], "success", result["status"])
        for index, number in enumerate((4, 5, 3, 1, 2)):
            image_info = result["outputs"][str(20 + index)]["images"][0]
            with urlopen(f"{SERVER_URL}/view?{urlencode(image_info)}", timeout=15) as response:
                image = Image.open(io.BytesIO(response.read())).convert("RGB")
            self.assertEqual(image.size, (64 + number * 8, 64))
            self.assertEqual(image.getpixel((0, 0)), (number * 17, 0, 0))

    def test_actual_router_reports_missing_source(self):
        result = self.execute({
            "1": {"class_type": "DMCanvasConversationImageOrder", "inputs": {"image_order": "[2]"}},
            "2": {"class_type": "PreviewImage", "inputs": {"images": ["1", 0]}},
        })
        self.assertEqual(result["status"]["status_str"], "error")
        self.assertTrue(any("source_2" in message[1].get("exception_message", "")
                            for message in result["status"]["messages"]))

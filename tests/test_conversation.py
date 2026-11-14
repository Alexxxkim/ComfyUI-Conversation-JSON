import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from collections import Counter


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "dmcanvas_conversation_json_tests"
SPECIFICATION = importlib.util.spec_from_file_location(
    PACKAGE_NAME, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
PACKAGE = importlib.util.module_from_spec(SPECIFICATION)
sys.modules[PACKAGE_NAME] = PACKAGE
SPECIFICATION.loader.exec_module(PACKAGE)
CORE = sys.modules[f"{PACKAGE_NAME}.conversation"]
CONVERTER = PACKAGE.NODE_CLASS_MAPPINGS["DMCanvasConversationJSONV2"]
ROUTER = PACKAGE.NODE_CLASS_MAPPINGS["DMCanvasConversationImageOrder"]


class ConversationTests(unittest.TestCase):
    def convert(self, conversation, **options):
        return CORE.format_conversation(conversation, **options)

    def test_final_schema_and_reverse_batch_order(self):
        payload, order, warnings, count = self.convert(
            "user: [1][2] 生成合照\nai: [3]\nuser: [4][5] 加入这两个人", region="[locale=en-AU]"
        )
        self.assertEqual(order, [4, 5, 3, 1, 2])
        self.assertEqual(payload, {
            "current_request": {"role": "user", "text": "[canvas_image_1][canvas_image_2] 加入这两个人"},
            "history": [
                {"role": "user", "text": "[canvas_image_4][canvas_image_5] 生成合照"},
                {"role": "assistant", "generation_status": "succeeded", "image_ids": ["canvas_image_3"]},
            ],
            "locale": "en-AU",
        })
        self.assertEqual((warnings, count), ([], 1))

    def test_screenshot_three_old_inputs_one_new_input(self):
        payload, order, _, _ = self.convert(
            "user: [图 1][图 2][图 3] 生成一张圣诞合照\nai: [图 4]\nuser: [图 5] 让他和火人圣诞合照"
        )
        self.assertEqual(order, [5, 4, 1, 2, 3])
        self.assertEqual(payload["history"][0]["text"], "[canvas_image_3][canvas_image_4][canvas_image_5] 生成一张圣诞合照")
        self.assertEqual(payload["history"][1]["image_ids"], ["canvas_image_2"])

    def test_current_request_is_not_duplicated_in_history(self):
        payload, order, _, _ = self.convert("user: 画猫\nai: [1]\nuser: 画狗")
        self.assertEqual(payload["current_request"], {"role": "user", "text": "画狗"})
        self.assertEqual(len(payload["history"]), 2)
        self.assertEqual(order, [1])

    def test_text_only_new_request(self):
        payload, order, _, _ = self.convert("user: Why not")
        self.assertEqual(payload, {"current_request": {"role": "user", "text": "Why not"}, "history": []})
        self.assertEqual(order, [])

    def test_image_only_current_request(self):
        payload, order, _, _ = self.convert("user: [1] 后空翻\nai: [2]\nuser: [3]")
        self.assertEqual(payload["current_request"]["text"], "[canvas_image_1]")
        self.assertEqual(order, [3, 2, 1])

    def test_multiline_user_text_and_interleaved_images_are_preserved(self):
        payload, order, _, _ = self.convert("user: 先用 [2] 的脸\n换到 [1] 上。\n  衣服不变  ")
        self.assertEqual(order, [2, 1])
        self.assertEqual(payload["current_request"]["text"], "先用 [canvas_image_1] 的脸\n换到 [canvas_image_2] 上。\n  衣服不变  ")

    def test_case_insensitive_roles_and_chinese_colons(self):
        payload, _, _, _ = self.convert("USER：[1] 猫\nASSISTANT：[2]\nUser：换背景")
        self.assertEqual(payload["history"][1]["generation_status"], "succeeded")

    def test_consecutive_users_are_not_merged(self):
        payload, _, _, _ = self.convert("user: 要真人\nuser: Human")
        self.assertEqual(payload["history"], [{"role": "user", "text": "要真人"}])

    def test_consecutive_assistant_events_are_preserved(self):
        payload, order, _, _ = self.convert("user: [1] 改图\nai: [2]\nai: cancelled\nai: [3]\nuser: 继续")
        self.assertEqual(order, [3, 2, 1])
        self.assertEqual([entry["generation_status"] for entry in payload["history"][1:]], ["succeeded", "cancelled", "succeeded"])

    def test_failed_and_cancelled_have_no_reason_text_or_empty_images(self):
        for status in ("failed", "cancelled", "canceled"):
            with self.subTest(status=status):
                payload, order, _, _ = self.convert(f"user: [1] 改图\nai: {status}\nuser: 再试")
                expected = "cancelled" if status == "canceled" else status
                self.assertEqual(payload["history"][1], {"role": "assistant", "generation_status": expected})
                self.assertEqual(order, [1])

    def test_cancelled_attempt_does_not_remove_previous_result(self):
        payload, order, _, _ = self.convert("user: [1] 加帽子\nai: [2]\nuser: 雪景\nai: cancelled\nuser: 改雨景")
        self.assertEqual(order, [2, 1])
        self.assertEqual(payload["history"][1]["image_ids"], ["canvas_image_1"])

    def test_multiple_results_keep_their_batch_order(self):
        payload, order, _, _ = self.convert("user: [1] 两个版本\nai: [2][3]\nuser: 用第二张结果")
        self.assertEqual(order, [2, 3, 1])
        self.assertEqual(payload["history"][1]["image_ids"], ["canvas_image_1", "canvas_image_2"])

    def test_same_source_image_is_deduplicated_by_most_recent_batch(self):
        payload, order, _, _ = self.convert("user: [1][2] 合照\nai: [3]\nuser: [2][4][2] 换脸")
        self.assertEqual(order, [2, 4, 3, 1])
        self.assertEqual(payload["current_request"]["text"], "[canvas_image_1][canvas_image_2][canvas_image_1] 换脸")

    def test_original_image_remains_addressable_after_edits(self):
        payload, order, _, _ = self.convert("user: [1] 兽人\nai: [2]\nuser: 猫耳\nai: [3]\nuser: 回到原图，只加猫耳")
        self.assertEqual(order, [3, 2, 1])
        self.assertEqual(payload["history"][0]["text"], "[canvas_image_3] 兽人")

    def test_region_is_independent_and_flat(self):
        payload, _, _, _ = self.convert("user: 为什么不行？", region="[ locale = zh-Hant-TW ]")
        self.assertEqual(payload["locale"], "zh-Hant-TW")
        self.assertNotIn("region", payload)
        self.assertEqual(payload["current_request"]["text"], "为什么不行？")

    def test_empty_region_is_omitted(self):
        for region in (None, "", " \t\n"):
            with self.subTest(region=region):
                payload, _, _, _ = self.convert("user: 画猫", region=region)
                self.assertNotIn("locale", payload)

    def test_locale_in_user_text_is_not_extracted(self):
        payload, _, _, _ = self.convert("user: 原样打印\n[locale=en-AU]")
        self.assertNotIn("locale", payload)
        self.assertEqual(payload["current_request"]["text"], "原样打印\n[locale=en-AU]")

    def test_literal_headers_and_image_like_text_can_be_escaped(self):
        payload, order, _, _ = self.convert("user: 原样打印\n\\ai: failed\n编号 \\[1]，图片 [2]")
        self.assertEqual(order, [2])
        self.assertEqual(payload["current_request"]["text"], "原样打印\nai: failed\n编号 [1]，图片 [canvas_image_1]")

    def test_auto_does_not_mistake_quoted_full_history_for_input_format(self):
        payload, _, _, _ = self.convert("user: 原样打印\n[1] 用户 · 2026-01-01 09:00:00\n这是一段引用")
        self.assertIn("这是一段引用", payload["current_request"]["text"])

    def test_thinking_placeholder_is_omitted_without_pending(self):
        payload, _, _, _ = self.convert("user: 要人类\nai: Thinking...\nuser: Human")
        self.assertEqual(payload["history"], [{"role": "user", "text": "要人类"}])
        self.assertNotIn("pending", json.dumps(payload))

    def test_full_history_auto_detection_and_success_text_removal(self):
        payload, order, _, _ = self.convert(
            "[1] 用户 · 2026-09-13 13:52:02\n[图1] 改图\n\n"
            "[2] AI · 2026-09-13 13:52:03\nDone! [图2]\n\n"
            "[3] 用户 · 2026-09-13 13:52:50\n保持原样"
        )
        self.assertEqual(order, [2, 1])
        self.assertNotIn("text", payload["history"][1])
        self.assertEqual(payload["history"][1]["image_ids"], ["canvas_image_1"])

    def test_all_exported_failure_reasons_collapse_to_failed(self):
        for reason in ("moderation", "transient", "quota_exceeded"):
            with self.subTest(reason=reason):
                payload, _, _, _ = self.convert(
                    f"[1] 用户 · 2026-01-01 00:00:00\n[图1] 改图\n"
                    f"[2] AI · 2026-01-01 00:00:01\nError.[image][生成失败:{reason}]\n"
                    "[3] 用户 · 2026-01-01 00:00:02\n再试"
                )
                self.assertEqual(payload["history"][1], {"role": "assistant", "generation_status": "failed"})

    def test_exported_cancellation_spellings_and_translation(self):
        for body in ("Generation cancelled", "Generation canceled", "Đã hủy quá trình tạo"):
            with self.subTest(body=body):
                payload, _, _, _ = self.convert(
                    f"[1] 用户 · 2026-01-01 00:00:00\n改图\n[2] AI · 2026-01-01 00:00:01\n{body}\n"
                    "[3] 用户 · 2026-01-01 00:00:02\n再试"
                )
                self.assertEqual(payload["history"][1]["generation_status"], "cancelled")

    def test_multiple_full_cases_are_selected_not_combined(self):
        text = "[1] 用户 · 2026-01-01 00:00:00\n画猫\n[1] 用户 · 2026-01-02 00:00:00\n画狗"
        payload, order, warnings, count = self.convert(text, case_index=2)
        self.assertEqual(payload["current_request"]["text"], "画狗")
        self.assertEqual(payload["history"], [])
        self.assertEqual((order, count), ([], 2))
        self.assertIn("未合并", warnings[0])

    def test_incomplete_history_is_preserved_and_warned(self):
        payload, _, warnings, _ = self.convert(
            "[1] AI · 2026-01-01 00:00:00\nDone [图1]\n[2] 用户 · 2026-01-01 00:00:01\n加帽子"
        )
        self.assertEqual(payload["history"][0]["role"], "assistant")
        self.assertTrue(any("缺少" in warning for warning in warnings))

    def test_mention_placeholder_is_preserved_and_warned(self):
        payload, _, warnings, _ = self.convert("user: 让 [提及用户] 戴帽子")
        self.assertIn("[提及用户]", payload["current_request"]["text"])
        self.assertTrue(any("人物身份" in warning for warning in warnings))

    def test_unknown_full_ai_text_is_omitted_without_inventing_status(self):
        payload, _, warnings, _ = self.convert(
            "[1] 用户 · 2026-01-01 00:00:00\n画猫\n[2] AI · 2026-01-01 00:00:01\nUnknown UI message\n"
            "[3] 用户 · 2026-01-01 00:00:02\n改成狗"
        )
        self.assertEqual(len(payload["history"]), 1)
        self.assertTrue(any("未推断" in warning for warning in warnings))

    def test_bom_and_crlf_are_supported(self):
        payload, _, _, _ = self.convert("\ufeffuser: 画猫\r\nai: [1]\r\nuser: 改狗\r\n")
        self.assertEqual(payload["current_request"]["text"], "改狗")

    def test_converter_does_not_limit_image_count(self):
        payload, order, _, _ = self.convert("user: " + "".join(f"[{number}]" for number in range(1, 16)))
        self.assertEqual(len(order), 15)
        self.assertIn("canvas_image_15", payload["current_request"]["text"])

    def test_invalid_inputs_have_actionable_errors(self):
        cases = [
            ({"conversation": None}, "必须是文本"),
            ({"conversation": ""}, "最后一条"),
            ({"conversation": "画猫"}, "简化输入"),
            ({"conversation": "user: "}, "不能为空"),
            ({"conversation": "user: 猫\nai: failed"}, "最后一条"),
            ({"conversation": "user: 猫\nai: cancelled"}, "最后一条"),
            ({"conversation": "user: [0]"}, "正整数"),
            ({"conversation": "user: 猫\nai: pending\nuser: 狗"}, "不支持"),
            ({"conversation": "user: 猫\nai: [1] failed\nuser: 狗"}, "只写图片"),
            ({"conversation": "user: 猫\nai: [1] failed\nuser: 狗", "input_format": "full"}, "完整历史"),
            ({"conversation": "user: 猫", "region": "en-AU"}, "region"),
            ({"conversation": "user: 猫", "region": "[locale=]"}, "region"),
            ({"conversation": "user: 猫", "region": 1}, "region"),
            ({"conversation": "user: 猫", "case_index": 2}, "只检测到"),
            ({"conversation": "user: 猫", "case_index": 0}, "从 1 开始"),
            ({"conversation": "user: 猫", "case_index": True}, "从 1 开始"),
            ({"conversation": "user: 猫", "input_format": "unknown"}, "input_format"),
        ]
        for arguments, error in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, error):
                    self.convert(**arguments)

    def test_conflicting_full_result_and_failure_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "同时含图片"):
            self.convert("[1] AI · 2026-01-01 00:00:00\n[图1][生成失败:moderation]\n"
                         "[2] 用户 · 2026-01-01 00:00:01\n再试")


class NodeTests(unittest.TestCase):
    def test_registration_does_not_override_existing_nodes(self):
        self.assertEqual(set(PACKAGE.NODE_CLASS_MAPPINGS), {
            "DMCanvasConversationJSONV2", "DMCanvasConversationJSONPrefixV2", "DMCanvasConversationImageOrder",
        })
        self.assertEqual(CONVERTER.__name__, "ConversationJSON")
        self.assertEqual(PACKAGE.NODE_DISPLAY_NAME_MAPPINGS["DMCanvasConversationJSONV2"],
                         "Conversation JSON · 对话上下文转 JSON")
        self.assertEqual(set(PACKAGE.NODE_CLASS_MAPPINGS), set(PACKAGE.NODE_DISPLAY_NAME_MAPPINGS))

    def test_converter_widgets_sockets_and_output_contract(self):
        inputs = CONVERTER.INPUT_TYPES()
        self.assertTrue(inputs["required"]["conversation"][1]["forceInput"])
        self.assertEqual(inputs["required"]["conversation"][1]["display_name"], "conversation")
        self.assertTrue(inputs["required"]["conversation"][1]["multiline"])
        self.assertFalse(inputs["required"]["conversation"][1]["dynamicPrompts"])
        self.assertTrue(inputs["optional"]["region"][1]["forceInput"])
        result = CONVERTER().convert("user: [1] 猫", region="[locale=en-AU]")
        self.assertEqual(len(result), len(CONVERTER.RETURN_TYPES))
        self.assertEqual(json.loads(result[1]), [1])
        self.assertEqual(json.loads(result[0])["locale"], "en-AU")
        self.assertEqual(result[3], 1)

    def test_router_matches_json_mapping_without_modifying_images(self):
        sources = {f"source_{number}": object() for number in range(1, 6)}
        result = ROUTER().reorder("[4, 5, 3, 1, 2]", **sources)
        self.assertEqual(len(result), 10)
        for index, number in enumerate((4, 5, 3, 1, 2)):
            self.assertIs(result[index], sources[f"source_{number}"])
        self.assertEqual(result[5:], (None,) * 5)

    def test_router_accepts_no_images(self):
        self.assertEqual(ROUTER().reorder("[]"), (None,) * 10)

    def test_router_missing_source_is_not_silently_substituted(self):
        with self.assertRaisesRegex(ValueError, "source_2"):
            ROUTER().reorder("[2, 1]", source_1=object())

    def test_router_rejects_more_than_ten_actual_outputs(self):
        with self.assertRaisesRegex(ValueError, "十路"):
            ROUTER().reorder(json.dumps(list(range(1, 12))))

    def test_invalid_image_orders_are_rejected(self):
        for order in ("", "not json", "null", "{}", "[0]", "[true]", '["1"]', "[1, 1]", "[1.0]"):
            with self.subTest(order=order):
                with self.assertRaises(ValueError):
                    CORE.parse_image_order(order)

    def test_example_workflow_uses_separate_conversation_and_region(self):
        workflow = json.loads((ROOT / "examples/conversation_json.workflow.json").read_text())
        converter = next(node for node in workflow["nodes"] if node["type"] == "DMCanvasConversationJSONV2")
        self.assertEqual(converter["widgets_values"], ["auto", 1])
        self.assertEqual([entry["name"] for entry in converter["inputs"]], ["conversation", "region"])
        self.assertEqual(converter["inputs"][0]["label"], "conversation")
        nodes = {node["id"]: node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        for slot, entry in enumerate(converter["inputs"]):
            link = links[entry["link"]]
            self.assertEqual(link[3:5], [converter["id"], slot])
            self.assertEqual(nodes[link[1]]["type"], "PrimitiveStringMultiline")
            self.assertIn(link[0], nodes[link[1]]["outputs"][link[2]]["links"])

    def test_input_label_extension_is_registered(self):
        self.assertEqual(PACKAGE.WEB_DIRECTORY, "./web")
        self.assertTrue((ROOT / PACKAGE.WEB_DIRECTORY / "conversation_input_labels.js").is_file())

    def test_example_workflow_shows_all_image_router_sockets(self):
        workflow = json.loads((ROOT / "examples/conversation_json.workflow.json").read_text())
        router = next(node for node in workflow["nodes"] if node["type"] == "DMCanvasConversationImageOrder")
        converter = next(node for node in workflow["nodes"] if node["type"] == "DMCanvasConversationJSONV2")
        self.assertEqual([entry["name"] for entry in router["inputs"]],
                         ["image_order"] + list(ROUTER.INPUT_TYPES()["optional"]))
        self.assertEqual([entry["name"] for entry in router["outputs"]], list(ROUTER.RETURN_NAMES))
        link = next(link for link in workflow["links"] if link[0] == router["inputs"][0]["link"])
        self.assertEqual(link[1:5], [converter["id"], 1, router["id"], 0])


@unittest.skipUnless(os.environ.get("DMCANVAS_HISTORY_FIXTURE"), "Set DMCANVAS_HISTORY_FIXTURE to audit the original export.")
class OriginalExportTests(unittest.TestCase):
    def test_every_original_case_preserves_user_messages_images_and_events(self):
        source = Path(os.environ["DMCANVAS_HISTORY_FIXTURE"]).read_text(encoding="utf-8")
        cases = CORE.parse_full(source)
        self.assertEqual(len(cases), 996)
        statuses = Counter()
        total_user_messages = 0
        for case_index, original in enumerate(cases, 1):
            with self.subTest(case_index=case_index):
                payload, order, _, count = CORE.format_conversation(source, input_format="full", case_index=case_index)
                self.assertEqual(count, 996)
                mapping = {number: f"canvas_image_{index}" for index, number in enumerate(order, 1)}
                expected_users = [CORE.IMAGE_REFERENCE.sub(
                    lambda match: f"[{mapping[int(match.group(1))]}]", message["text"]
                ) for message in original if message["role"] == "user"]
                actual_users = [message["text"] for message in payload["history"] if message["role"] == "user"]
                actual_users.append(payload["current_request"]["text"])
                self.assertEqual(actual_users, expected_users)
                total_user_messages += len(actual_users)
                expected_images = [mapping[number] for message in original if message["role"] == "assistant"
                                   for number in CORE.image_numbers(message["text"])]
                actual_images = [image for message in payload["history"] for image in message.get("image_ids", [])]
                self.assertEqual(actual_images, expected_images)
                for message in payload["history"]:
                    if message["role"] == "assistant":
                        statuses[message["generation_status"]] += 1
                        self.assertNotIn("text", message)
                        self.assertNotIn("failure_reason", message)
                self.assertEqual(set(payload["current_request"]), {"role", "text"})
        self.assertEqual(total_user_messages, 1936)
        self.assertEqual(statuses, {"succeeded": 455, "failed": 435, "cancelled": 116})

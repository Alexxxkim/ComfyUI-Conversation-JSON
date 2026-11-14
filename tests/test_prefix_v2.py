import json
import unittest

from test_conversation import CONVERTER, PACKAGE, ROOT


CONVERTER_V2 = PACKAGE.NODE_CLASS_MAPPINGS["DMCanvasConversationJSONPrefixV2"]
EXAMPLES = [
    ("Create a sticker of a blonde haired girl sleeping", "a blonde haired girl sleeping", "R1", []),
    ("make a sticker of a blonde haired girl sleeping", "make a sticker of a blonde haired girl sleeping", None, []),
    ("Create a sticker of a hamster with steam coming out of his ears coz hes so angy and the japanese angry emoji thing on his face",
     "a hamster with steam coming out of his ears coz hes so angy and the japanese angry emoji thing on his face", "R1", []),
    ("Remix [图1] Make it a sticker", "[canvas_image_1] Make it a sticker", "R2", [1]),
    ("Create a sticker of [图1] wearing a dress", "[canvas_image_1] wearing a dress", "R1", [1]),
    ("Create a sticker of [图1] with a thick moustache", "[canvas_image_1] with a thick moustache", "R1", [1]),
    ("Create a sticker of [图1] with a thick moustache and make it a sticker",
     "[canvas_image_1] with a thick moustache and make it a sticker", "R1", [1]),
    ("Create a sticker of me holding the blue think[图1] [图2]",
     "me holding the blue think[canvas_image_1] [canvas_image_2]", "R1", [1, 2]),
    ("Create a sticker of [图1] [图2]", "[canvas_image_1] [canvas_image_2]", "R1", [1, 2]),
    ("Create a sticker of [图1] [图2]", "[canvas_image_1] [canvas_image_2]", "R1", [1, 2]),
    ("Create a sticker of [图1] [图2]drinking beer",
     "[canvas_image_1] [canvas_image_2]drinking beer", "R1", [1, 2]),
    ("[图1] [图2]make it a sticker", "[canvas_image_1] [canvas_image_2]make it a sticker", None, [1, 2]),
]
HISTORY_CASE = (
    "[1] 用户 · 2026-09-18 12:32:58\n"
    "Create a sticker of [图1] make him extremely angry like someone stole his toy\n\n"
    "[2] AI · 2026-09-18 12:32:58\n"
    "Here's that fiery angry sticker, all dramatic frustration as if his favourite toy got snatched![图2]\n\n"
    "[3] 用户 · 2026-09-18 12:34:28\nRemove the emojis"
)
HISTORY_PAYLOAD = {
    "current_request": {"role": "user", "text": "Remove the emojis"},
    "history": [
        {"role": "user", "text": "[canvas_image_2] make him extremely angry like someone stole his toy", "prefix": "R1"},
        {"role": "assistant", "generation_status": "succeeded", "image_ids": ["canvas_image_1"]},
    ],
}


class PrefixV2Tests(unittest.TestCase):
    def test_documented_examples_match_actual_node_outputs(self):
        examples = json.loads((ROOT / "examples/prefix_v2_outputs.json").read_text(encoding="utf-8"))
        self.assertEqual(len(examples), len(EXAMPLES))
        for index, example in enumerate(examples, 1):
            with self.subTest(example=index):
                self.assertEqual(example["example"], index)
                self.assertEqual(example["input"], EXAMPLES[index - 1][0])
                result = CONVERTER_V2().convert(f"user: {example['input']}")
                self.assertEqual(example["outputs"], {
                    "json": json.loads(result[0]), "image_order": json.loads(result[1]),
                    "warnings": result[2], "case_count": result[3],
                })

    def test_all_twelve_user_examples(self):
        for index, (source, text, prefix, order) in enumerate(EXAMPLES, 1):
            with self.subTest(example=index):
                result = CONVERTER_V2().convert(f"user: {source}")
                current_request = {"role": "user", "text": text}
                if prefix is not None:
                    current_request["prefix"] = prefix
                self.assertEqual(json.loads(result[0]), {"current_request": current_request, "history": []})
                self.assertEqual(json.loads(result[1]), order)
                self.assertEqual(result[2:], ("", 1))

    def test_prefix_does_not_require_a_separator(self):
        for source, text, prefix in (
            ("Create a sticker ofa cat", "a cat", "R1"),
            ("Create a sticker of[图1]", "[canvas_image_1]", "R1"),
            ("Remix[图1]", "[canvas_image_1]", "R2"),
            ("RemixMake it a sticker", "Make it a sticker", "R2"),
        ):
            with self.subTest(source=source):
                result = CONVERTER_V2().convert(f"user: {source}")
                self.assertEqual(json.loads(result[0])["current_request"],
                                 {"role": "user", "text": text, "prefix": prefix})

    def test_only_exact_prefix_at_start_matches(self):
        for source in (
            "create a sticker of a cat", "CREATE A STICKER OF a cat", "remix[图1]",
            "Please Create a sticker of a cat", "[图1] Remix it", "Create a sticker o",
            "First line\nRemix [图1]", "Make a sticker of a cat",
        ):
            with self.subTest(source=source):
                self.assertEqual(CONVERTER_V2().convert(f"user: {source}"),
                                 CONVERTER().convert(f"user: {source}"))

    def test_only_one_prefix_and_its_following_whitespace_are_removed(self):
        for source, text, prefix in (
            ("Create a sticker of   a cat  ", "a cat  ", "R1"),
            ("Remix\t\n  [图1]\n  keep this indentation  ",
             "[canvas_image_1]\n  keep this indentation  ", "R2"),
            ("Remix Create a sticker of a cat", "Create a sticker of a cat", "R2"),
            ("Create a sticker of Remix[图1]", "Remix[canvas_image_1]", "R1"),
            ("Create a sticker of", "", "R1"),
            ("Remix", "", "R2"),
        ):
            with self.subTest(source=source):
                result = CONVERTER_V2().convert(f"user: {source}")
                self.assertEqual(json.loads(result[0])["current_request"],
                                 {"role": "user", "text": text, "prefix": prefix})

    def test_original_node_keeps_all_prefixes(self):
        for source, _, prefix, _ in EXAMPLES:
            with self.subTest(source=source):
                current_request = json.loads(CONVERTER().convert(f"user: {source}")[0])["current_request"]
                self.assertEqual(set(current_request), {"role", "text"})
                if prefix is not None:
                    self.assertTrue(current_request["text"].startswith("Create a sticker of" if prefix == "R1" else "Remix"))

    def test_all_twelve_user_examples_keep_prefix_metadata_when_moved_to_history(self):
        for index, (source, text, prefix, order) in enumerate(EXAMPLES, 1):
            with self.subTest(example=index):
                result = CONVERTER_V2().convert(f"user: {source}\nai: [99]\nuser: Remove the emojis")
                history_text = text.replace("[canvas_image_2]", "[canvas_image_3]").replace(
                    "[canvas_image_1]", "[canvas_image_2]"
                )
                history_request = {"role": "user", "text": history_text}
                if prefix is not None:
                    history_request["prefix"] = prefix
                self.assertEqual(json.loads(result[0]), {
                    "current_request": {"role": "user", "text": "Remove the emojis"},
                    "history": [history_request, {
                        "role": "assistant", "generation_status": "succeeded", "image_ids": ["canvas_image_1"],
                    }],
                })
                self.assertEqual(json.loads(result[1]), [99, *order])
                self.assertEqual(result[2:], ("", 1))

    def test_user_provided_full_history_case(self):
        result = CONVERTER_V2().convert(HISTORY_CASE)
        self.assertEqual(json.loads(result[0]), HISTORY_PAYLOAD)
        self.assertEqual(json.loads(result[1]), [2, 1])
        self.assertEqual(result[2:], ("", 1))

    def test_all_user_messages_are_processed_without_changing_assistant_events(self):
        conversation = (
            "user: Create a sticker of[图1] make it a sticker\nai: [图2]\n"
            "user: Remix[图2]  angry  \nai: failed\n"
            "user: [图1] Remix it\nai: cancelled\n"
            "user: Create a sticker of Remix[图2]"
        )
        result = CONVERTER_V2().convert(conversation)
        self.assertEqual(json.loads(result[0]), {
            "current_request": {"role": "user", "text": "Remix[canvas_image_1]", "prefix": "R1"},
            "history": [
                {"role": "user", "text": "[canvas_image_2] make it a sticker", "prefix": "R1"},
                {"role": "assistant", "generation_status": "succeeded", "image_ids": ["canvas_image_1"]},
                {"role": "user", "text": "[canvas_image_1]  angry  ", "prefix": "R2"},
                {"role": "assistant", "generation_status": "failed"},
                {"role": "user", "text": "[canvas_image_2] Remix it"},
                {"role": "assistant", "generation_status": "cancelled"},
            ],
        })
        self.assertEqual(json.loads(result[1]), [2, 1])

    def test_no_matching_prefixes_preserve_the_complete_original_output(self):
        conversation = "user: make a sticker of [1]\nai: [2]\nuser: Please Remix it\nai: failed\nuser: [1] 继续"
        self.assertEqual(CONVERTER_V2().convert(conversation), CONVERTER().convert(conversation))

    def test_original_node_does_not_process_history_prefixes(self):
        result = CONVERTER().convert(HISTORY_CASE)
        payload = json.loads(result[0])
        self.assertEqual(payload["history"][0], {
            "role": "user", "text": "Create a sticker of [canvas_image_2] make him extremely angry like someone stole his toy",
        })
        self.assertEqual(payload["history"][1], HISTORY_PAYLOAD["history"][1])
        self.assertEqual(payload["current_request"], HISTORY_PAYLOAD["current_request"])

    def test_locale_order_warnings_count_and_assistant_history_are_unchanged(self):
        conversation = (
            "user: Create a sticker of [图1][图2] [提及用户]\nai: [图3]\n"
            "user: Remix [图2][图4][图2] change it"
        )
        options = {"region": "[locale=en-AU]"}
        original_result = CONVERTER().convert(conversation, **options)
        new_result = CONVERTER_V2().convert(conversation, **options)
        original = json.loads(original_result[0])
        updated = json.loads(new_result[0])
        self.assertEqual(updated["history"][0], {
            "role": "user", "text": "[canvas_image_4][canvas_image_1] [提及用户]", "prefix": "R1",
        })
        self.assertEqual(updated["history"][1], original["history"][1])
        self.assertEqual(updated["locale"], original["locale"])
        self.assertEqual(new_result[1:], original_result[1:])
        self.assertEqual(json.loads(new_result[1]), [2, 4, 3, 1])
        self.assertEqual(updated["current_request"], {
            "role": "user", "text": "[canvas_image_1][canvas_image_2][canvas_image_1] change it", "prefix": "R2",
        })

    def test_full_format_and_case_selection_are_unchanged(self):
        conversation = (
            "[1] 用户 · 2026-11-14 00:00:00\nCreate a sticker of a cat\n"
            "[1] 用户 · 2026-11-14 00:00:01\nRemix[图3] a dog"
        )
        original_result = CONVERTER().convert(conversation, input_format="full", case_index=2)
        new_result = CONVERTER_V2().convert(conversation, input_format="full", case_index=2)
        self.assertEqual(new_result[1:], original_result[1:])
        self.assertEqual(json.loads(new_result[0]), {
            "current_request": {"role": "user", "text": "[canvas_image_1] a dog", "prefix": "R2"}, "history": [],
        })

    def test_input_and_output_contract_is_identical_to_original(self):
        self.assertEqual(CONVERTER_V2.INPUT_TYPES(), CONVERTER.INPUT_TYPES())
        self.assertEqual(CONVERTER_V2.RETURN_TYPES, CONVERTER.RETURN_TYPES)
        self.assertEqual(CONVERTER_V2.RETURN_NAMES, CONVERTER.RETURN_NAMES)
        self.assertEqual(CONVERTER_V2.CATEGORY, CONVERTER.CATEGORY)

    def test_validation_errors_are_not_bypassed(self):
        for source in ("user: ", "user: Remix[图0]", "user: Create a sticker of a cat\nai: failed"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    CONVERTER_V2().convert(source)

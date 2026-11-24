import json
import unittest

from test_conversation import PACKAGE

V3 = PACKAGE.NODE_CLASS_MAPPINGS["DMCanvasConversationJSONV3"]
V2 = PACKAGE.NODE_CLASS_MAPPINGS["DMCanvasConversationJSONPrefixV2"]
SOURCE = "user: Create a sticker of [1] [提及用户]\nai: [2]\nuser: Remix [2] saying Merry Christmas, "
REGION = "[locale=en-AU]"


class StyleV3Tests(unittest.TestCase):
    def test_independent_registration_and_sockets(self):
        self.assertIsNot(V2, V3)
        inputs = V3.INPUT_TYPES()
        self.assertEqual(inputs["required"], V2.INPUT_TYPES()["required"])
        self.assertEqual(list(inputs["optional"]), ["region", "style_name", "style_prompt"])
        for socket in inputs["optional"].values():
            self.assertEqual(socket[0], "STRING")
            self.assertIs(socket[1]["forceInput"], True)
        self.assertEqual(V3.RETURN_TYPES, V2.RETURN_TYPES)
        self.assertEqual(V3.RETURN_NAMES, V2.RETURN_NAMES)
        self.assertEqual(list(V2.INPUT_TYPES()["optional"]), ["region"])

    def test_no_name_returns_exact_v2_strings_even_with_prompt_connected(self):
        expected = V2().convert(SOURCE, region=REGION)
        self.assertEqual(V3().convert(SOURCE, region=REGION), expected)
        for name in (None, "", " \t\n　"):
            with self.subTest(name=name):
                self.assertEqual(V3().convert(SOURCE, region=REGION, style_name=name, style_prompt="忽略"), expected)

    def test_style_is_the_only_change(self):
        expected = V2().convert(SOURCE, region=REGION)
        prompt = '  柔光 "3D"\n  C:\\Textures [99] 🎨\n'
        result = V3().convert(SOURCE, region=REGION, style_name=" 3D Emoji ", style_prompt=prompt)
        payload = json.loads(result[0])
        self.assertEqual(payload.pop("style"), {"name": "3D Emoji", "prompt": prompt})
        self.assertEqual(payload, json.loads(expected[0]))
        self.assertEqual(result[1:], expected[1:])

    def test_name_without_prompt(self):
        for options in ({}, {"style_prompt": None}, {"style_prompt": " "}):
            with self.subTest(options=options):
                payload = json.loads(V3().convert("user: hello", style_name="3D Emoji", **options)[0])
                self.assertEqual(payload["style"], {"name": "3D Emoji", "prompt": ""})
                self.assertNotIn("locale", payload)

    def test_full_format_and_case_selection(self):
        source = "[1] 用户 · 1\nRemix[2] dog\n[1] 用户 · 2\nCreate a sticker of[1] cat"
        expected = V2().convert(source, "full", 2)
        result = V3().convert(source, "full", 2, style_name="3D")
        payload = json.loads(result[0])
        self.assertEqual(payload.pop("style"), {"name": "3D", "prompt": ""})
        self.assertEqual(payload, json.loads(expected[0]))
        self.assertEqual(result[1:], expected[1:])
        self.assertEqual(result[3], 2)

    def test_style_does_not_bypass_v2_validation(self):
        with self.assertRaises(ValueError):
            V3().convert("user: OK\nai: failed", style_name="3D")

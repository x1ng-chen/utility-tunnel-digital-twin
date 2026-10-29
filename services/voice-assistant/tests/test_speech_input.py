import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xiaozhi_adapter.utility_tunnel.speech_input import normalize_business_text, normalize_latest_user_turn


class BusinessInputTests(unittest.TestCase):
    def test_explicit_five_station_spellings(self):
        cases = {
            "P一站点现在是什么状态": "P1站点现在是什么状态",
            "查询p 2": "查询P2", "Ｐ３检测点": "P3检测点",
            "皮四站点有告警吗": "P4站点有告警吗",
            "第一检测点的烟雾情况": "P1检测点的烟雾情况",
            "一号站现在怎样": "P1站现在怎样",
            "第五个监测点温度多少": "P5监测点温度多少",
            "二号站点和P四比较": "P2站点和P4比较",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_business_text(raw), expected)

    def test_device_spelling_preserves_physical_label_identity(self):
        for raw, expected in {
            "M Q 二-零一烟雾": "MQ2-01烟雾", "mq四 - 二的数值": "MQ4-02的数值",
            "CO-零二": "CO-02", "ctrl - 一": "CTRL-01", "FAN-二": "FAN-02",
            "LEVEL-四": "LEVEL-04",
        }.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_business_text(raw), expected)

    def test_explicit_zero_padded_spoken_ids_without_dash(self):
        # A real local ASR smoke fixture returned "mq 二零一".
        for raw, expected in {
            "mq 二零一传感器": "MQ2-01传感器", "MQ 二 零 一": "MQ2-01",
            "MQ201探头": "MQ2-01探头", "CTRL零二状态": "CTRL-02状态",
            "CO2浓度": "CO2浓度", "MQ2零九": "MQ2零九", "FAN09": "FAN09",
            "MQ2015": "MQ2015", "CO-12": "CO-12",
        }.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_business_text(raw), expected)

    def test_missing_ambiguous_unsupported_and_ordinary_numbers_are_not_guessed(self):
        unchanged = ["点现在是什么状态", "哪个站点正常", "P10和AP1", "P一零", "P1A",
            "第六检测点", "温度一度，一氧化碳和二氧化碳", "CO2浓度",
            "CO-09", "MQ4-09", "LEVEL-05", "一号站台", "地铁一号站现在怎样",
            "一号风机", "三点五摄氏度", "你好小管", "不用说了", "闭嘴",
            '{"content": "P一", "role": "user"}']
        for raw in unchanged:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_business_text(raw), raw)

    def test_multi_digit_unknown_and_fullwidth_identifier_boundaries(self):
        for raw in ["十一号站现在状态", "二十一号检测点", "11号站", "１１号站",
                    "１一号站", "一点一号站", "1.1号站", "ＡＰ１检测点",
                    "P一Ａ", "AP一", "p一.一", "MQ二十", "MQ四十", "MQ二十一",
                    "MQ二零九", "MQ2零九", "MQ2AB", "MQ二三"]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_business_text(raw), raw)

    def test_latest_turn_copy_preserves_raw_history_and_untrusted_roles(self):
        dialogue = [{"role": "user", "content": "P一"},
            {"role": "assistant", "content": "P二"},
            {"role": "tool", "content": "P三"},
            {"role": "user", "content": "P四状态", "extra": "untrusted"}]
        result = normalize_latest_user_turn(dialogue)
        self.assertEqual(result[-1]["content"], "P4状态")
        self.assertEqual(dialogue[-1]["content"], "P四状态")
        self.assertEqual(result[:-1], dialogue[:-1])
        for invalid in [None, "P一", [], [None], [{"role": "assistant", "content": "P一"}]]:
            self.assertIs(normalize_latest_user_turn(invalid), invalid)

    def test_provider_sends_normalized_turn_to_real_bridge_boundary(self):
        stubs = {name: types.ModuleType(name) for name in
            ["core", "core.providers", "core.providers.llm", "core.providers.llm.base"]}
        stubs["core.providers.llm.base"].LLMProviderBase = object
        path = Path(__file__).resolve().parents[1] / "xiaozhi_adapter/utility_tunnel/utility_tunnel.py"
        spec = importlib.util.spec_from_file_location("xiaozhi_adapter.utility_tunnel._input_test_provider", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(module)
        seen = []
        provider = object.__new__(module.LLMProvider)
        provider.client = SimpleNamespace(ask=lambda dialogue:
            (seen.append(dialogue) or SimpleNamespace(text="收到")))
        raw = [{"role": "user", "content": "查询P一"}]
        self.assertEqual(list(provider.response("test", raw)), ["收到"])
        self.assertEqual(seen[0][-1]["content"], "查询P1")
        self.assertEqual(raw[-1]["content"], "查询P一")


if __name__ == "__main__":
    unittest.main()

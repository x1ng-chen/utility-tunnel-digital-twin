"""Offline identity/diagnostic checks. Never opens a serial port."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("ut_sensor_diagnostics",HERE.parent/"verify_sensors.py")
diagnostics=importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)

class DiagnosticTests(unittest.TestCase):
    def test_new_frame_distinguishes_missing_and_held_observations(self):
        frame={"schema":"ut.telemetry.v1","controllerId":"CTRL-01","seq":17,
            "clockSource":"receiver-estimated","readings":[
                {"assetCode":"MQ2-05","metric":"smoke.alarm","value":1,"unit":"bool",
                 "quality":"suspect","sampleAgeMs":1200,"eventLatched":True},
                {"assetCode":"ENV-03","metric":"temperature","value":0,"unit":"degC",
                 "quality":"missing","sampleAgeMs":655350}]}
        text=diagnostics.summarize(frame,1)
        self.assertIn("OBSERVED EVENT, NOT CURRENT LEVEL",text)
        self.assertIn("temperature=--degC",text)
        self.assertIsNone(diagnostics.summarize(frame,2))

    def test_legacy_capture_and_non_payload_lines_remain_separate(self):
        text=diagnostics.summarize({"board":4,"seq":1,"slots":[{"id":1,"v":1,"a":0,"s":3}]},4)
        self.assertIn("MQ2-01=1",text)
        self.assertIn("observed-event-held",text)
        self.assertIsNone(diagnostics.summarize({"board":4,"busErrors":0},4))
        self.assertIsNone(diagnostics.summarize([],4))

    def test_every_wire_id_matches_firmware_tag_and_platform_asset(self):
        board_source=(HERE.parent/"Core/Src/board_config.c").read_text(encoding="utf-8")
        sensor_tags={int(i):tag for i,tag in re.findall(r'\{\s*(\d+)U,\s*SENSOR_\w+,\s*\d+U,\s*"([^"]+)"',board_source)}
        self.assertEqual(sensor_tags,diagnostics.TAGS)
        inventory=json.loads((ROOT/"backend/operations/agent_catalog/station-inventory.json").read_text(encoding="utf-8"))
        by_tag={b["physicalTag"]:b for b in inventory["bindings"]}
        wire=(HERE.parent/"gateway/include/device_map.h").read_text(encoding="utf-8")
        entries=re.findall(r'\{"([^"]*)","([^"]*)","([^"]*)",(\d+)\}',wire)
        self.assertEqual(len(entries),32)
        for i,entry in enumerate(entries[1:],1):
            asset,metric,unit,board=entry
            expected=by_tag[sensor_tags[i]]
            self.assertEqual((asset,f"CTRL-0{board}"),(expected["assetCode"],expected["controllerId"]))
            if i<=20:
                self.assertEqual(metric,["smoke.alarm","methane.raw","co.raw","flame.alarm"][(i-1)%4])
            elif i<=24:self.assertEqual((metric,unit),("temperature","degC"))
            elif i<=28:self.assertEqual((metric,unit),("level.detected","bool"))
            else:self.assertEqual((metric,unit),("oxygen.raw","adc"))

if __name__=="__main__":
    unittest.main()

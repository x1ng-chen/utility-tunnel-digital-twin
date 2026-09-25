from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE_A = (ROOT / "Core" / "Src" / "node_a.c").read_text(encoding="utf-8")
MSP = (ROOT / "Core" / "Src" / "stm32f1xx_hal_msp.c").read_text(encoding="utf-8")


class NodeAGasChannelContractTests(unittest.TestCase):
    def test_physical_adc_channel_assignment(self):
        self.assertIn("GasAdc_ReadRaw(ADC_CHANNEL_13, &oxygen_raw)", NODE_A)
        self.assertIn("GasAdc_ReadRaw(ADC_CHANNEL_12, &methane_raw)", NODE_A)
        self.assertIn("GasAdc_ReadRaw(ADC_CHANNEL_11, &co_raw)", NODE_A)

    def test_all_three_gas_pins_are_analog_inputs(self):
        self.assertIn(
            "GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_3",
            MSP,
        )

    def test_co_evidence_is_published(self):
        self.assertIn('\\"metric\\":\\"co.raw\\"', NODE_A)
        self.assertIn('\\"metric\\":\\"co.voltage\\"', NODE_A)


if __name__ == "__main__":
    unittest.main()

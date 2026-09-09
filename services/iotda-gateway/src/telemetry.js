const NORMAL_AIR_OXYGEN_PERCENT = 20.9;
const AO02_TYPICAL_AIR_MILLIVOLTS = 11;

/**
 * Calculate oxygen from the measured AO-02 voltage using the data-sheet
 * typical air output as the single-point reference: 11 mV == 20.9 %Vol O2.
 * Raw ADC and voltage readings remain in the frame for traceability.
 */
export function addCalculatedOxygenConcentration(telemetry) {
  const voltageReading = telemetry.readings.find((reading) =>
    reading.assetCode === 'GAS-01' && reading.metric === 'oxygen.voltage' && reading.unit === 'mV');
  const alreadyEstimated = telemetry.readings.some((reading) =>
    reading.assetCode === 'GAS-01' && reading.metric === 'oxygen.concentration');
  if (!voltageReading || alreadyEstimated) return telemetry;
  const calculated = Number(voltageReading.value) * NORMAL_AIR_OXYGEN_PERCENT / AO02_TYPICAL_AIR_MILLIVOLTS;
  const concentration = Math.round(Math.min(100, Math.max(0, calculated)) * 10) / 10;
  return {
    ...telemetry,
    readings: [
      ...telemetry.readings,
      {
        assetCode: 'GAS-01',
        metric: 'oxygen.concentration',
        value: concentration,
        unit: '%Vol',
        quality: 'suspect',
      },
    ],
  };
}

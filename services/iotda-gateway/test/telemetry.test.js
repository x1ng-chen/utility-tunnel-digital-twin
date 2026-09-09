import assert from 'node:assert/strict';
import test from 'node:test';
import { addCalculatedOxygenConcentration } from '../src/telemetry.js';

test('calculates oxygen from the measured voltage while retaining raw evidence', () => {
  const source = {
    schema: 'ut.telemetry.v1',
    readings: [
      { assetCode: 'GAS-01', metric: 'oxygen.raw', value: 8, unit: 'adc', quality: 'suspect' },
      { assetCode: 'GAS-01', metric: 'oxygen.voltage', value: 6.447, unit: 'mV', quality: 'suspect' },
    ],
  };

  const result = addCalculatedOxygenConcentration(source);

  assert.equal(source.readings.length, 2);
  assert.equal(result.readings.length, 3);
  assert.deepEqual(result.readings[2], {
    assetCode: 'GAS-01', metric: 'oxygen.concentration', value: 12.2, unit: '%Vol', quality: 'suspect',
  });
});

test('does not duplicate an existing oxygen concentration', () => {
  const source = {
    schema: 'ut.telemetry.v1',
    readings: [
      { assetCode: 'GAS-01', metric: 'oxygen.raw', value: 8, unit: 'adc', quality: 'suspect' },
      { assetCode: 'GAS-01', metric: 'oxygen.concentration', value: 19.8, unit: '%Vol', quality: 'good' },
    ],
  };

  assert.equal(addCalculatedOxygenConcentration(source), source);
});

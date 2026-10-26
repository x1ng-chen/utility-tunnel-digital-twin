import type { ControllerAction } from '../services/api';
import type { Telemetry } from '../types';

export function outputOwner(action: ControllerAction, protocol: string, selected?: string): string {
  if (protocol === 'legacy') return 'CTRL-01';
  if (protocol !== 'four-controller-v2') throw new Error('控制配置尚未加载。');
  if (action === 'fan_pwm') return 'CTRL-04';
  if (action === 'fan2_pwm') return 'CTRL-02';
  if (action.startsWith('led_') || action.startsWith('buzzer_')) return 'CTRL-03';
  const allowed = action === 'auto' ? ['CTRL-02', 'CTRL-03', 'CTRL-04'] : ['CTRL-02', 'CTRL-04'];
  if (!selected || !allowed.includes(selected)) throw new Error('必须选择有此输出的控制器。');
  return selected;
}

export function feedbackValue(reading: Pick<Telemetry, 'value' | 'recordedAt' | 'quality'> | undefined, nowMs: number, digits = 0) {
  if (!reading || !Number.isFinite(reading.value) || !['good', 'suspect'].includes(reading.quality)) return '—';
  const age = nowMs - Date.parse(reading.recordedAt);
  if (!Number.isFinite(age) || age < 0 || age > 10000) return '—';
  return reading.value.toFixed(digits) + (reading.quality === 'suspect' ? '*' : '');
}

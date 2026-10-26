import { describe, expect, it } from 'vitest';
import { feedbackValue, outputOwner } from './controllerControls';
describe('physical output ownership and feedback', () => {
  it('uses the two actual fan owners and the separate lighting owner', () => {
    expect(outputOwner('fan_pwm', 'four-controller-v2')).toBe('CTRL-04');
    expect(outputOwner('fan2_pwm', 'four-controller-v2')).toBe('CTRL-02');
    expect(outputOwner('led_blue', 'four-controller-v2')).toBe('CTRL-03');
    expect(outputOwner('relay_on', 'four-controller-v2', 'CTRL-02')).toBe('CTRL-02');
    expect(outputOwner('relay_off', 'four-controller-v2', 'CTRL-04')).toBe('CTRL-04');
    expect(outputOwner('fan2_pwm', 'legacy')).toBe('CTRL-01');
  });
  it('does not invent an owner for ambiguous relay actions or unknown configuration', () => {
    expect(() => outputOwner('relay_on', 'four-controller-v2')).toThrow();
    expect(() => outputOwner('relay_on', 'four-controller-v2', 'CTRL-03')).toThrow();
    expect(() => outputOwner('fan_pwm', 'unknown')).toThrow();
  });
  it('expires a formerly fresh feedback value and distinguishes unverified data', () => {
    const now = Date.parse('2026-10-27T10:00:00Z');
    const reading = { value: 1200, quality: 'good' as const, recordedAt: new Date(now - 1000).toISOString() };
    expect(feedbackValue(reading, now)).toBe('1200');
    expect(feedbackValue({ ...reading, quality: 'suspect' }, now)).toBe('1200*');
    expect(feedbackValue(reading, now + 10001)).toBe('—');
    expect(feedbackValue({ ...reading, quality: 'missing' }, now)).toBe('—');
    expect(feedbackValue({ ...reading, quality: 'bad' }, now)).toBe('—');
    expect(feedbackValue({ ...reading, recordedAt: new Date(now + 1).toISOString() }, now)).toBe('—');
    expect(feedbackValue(undefined, now)).toBe('—');
  });
});

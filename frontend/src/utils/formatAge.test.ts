import {formatAge} from './formatAge.ts';

const NOW = Date.parse('2026-10-21T12:00:00Z');

describe('formatAge', () => {
  it.each([
    ['2026-10-21T11:59:30Z', 'just now'],
    ['2026-10-21T12:05:00Z', 'just now'],
    ['2026-10-21T11:59:00Z', '1 minute ago'],
    ['2026-10-21T11:15:00Z', '45 minutes ago'],
    ['2026-10-21T09:00:00Z', '3 hours ago'],
    ['2026-10-20T11:00:00Z', 'yesterday'],
  ])('describes %s as "%s"', (time, expected) => {
    expect(formatAge(time, NOW)).toBe(expected);
  });

  it('handles an unreadable timestamp', () => {
    expect(formatAge('not a date', NOW)).toBe('at an unknown time');
  });
});

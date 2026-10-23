const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['day', 24 * 60 * 60 * 1000],
  ['hour', 60 * 60 * 1000],
  ['minute', 60 * 1000],
];

const formatter = new Intl.RelativeTimeFormat('en', {numeric: 'auto'});

/**
 * Describes how long ago an ISO timestamp was, e.g. "3 hours ago". Anything
 * under a minute (or in the future, from clock skew) is "just now".
 */
export function formatAge(isoTime: string, now: number = Date.now()): string {
  const elapsed = now - Date.parse(isoTime);
  if (!Number.isFinite(elapsed)) return 'at an unknown time';
  for (const [unit, size] of UNITS) {
    if (elapsed >= size) {
      return formatter.format(-Math.floor(elapsed / size), unit);
    }
  }
  return 'just now';
}

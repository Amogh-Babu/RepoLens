/**
 * Per-viewer "already seen" flags, such as the first-run tour. Kept in
 * localStorage, which can be missing or throw (private windows, blocked
 * site data); then nothing is remembered and the page still works.
 */

const PREFIX = 'repolens.seen.';

export type SeenFlag = 'workspace-tour';

export function hasSeen(flag: SeenFlag): boolean {
  try {
    return globalThis.localStorage?.getItem(PREFIX + flag) === '1';
  } catch {
    return false;
  }
}

export function markSeen(flag: SeenFlag): void {
  try {
    globalThis.localStorage?.setItem(PREFIX + flag, '1');
  } catch {
    // Not remembered; the tour may show again next time.
  }
}

export function clearSeen(flag: SeenFlag): void {
  try {
    globalThis.localStorage?.removeItem(PREFIX + flag);
  } catch {
    // Nothing to clear.
  }
}

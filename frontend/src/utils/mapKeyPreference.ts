/**
 * Whether the map's key is open, remembered per viewer in localStorage.
 * Open the first time; if storage is missing or throws (private windows,
 * blocked site data), it simply opens every time.
 */

const STORAGE_KEY = 'repolens.map-key';

export function loadKeyOpen(): boolean {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) !== 'closed';
  } catch {
    return true;
  }
}

export function saveKeyOpen(open: boolean): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, open ? 'open' : 'closed');
  } catch {
    // Not remembered; the key opens again next time.
  }
}

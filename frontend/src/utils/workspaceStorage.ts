import type {Analysis} from '../api/types.ts';

const RECENT_REPOS_KEY = 'repolens.recentRepos';
const VIEW_STATE_PREFIX = 'repolens.viewState.';

export const MAX_RECENT_REPOS = 6;

export type WorkspaceTab = 'overview' | 'reading' | 'files';

export interface RecentRepo {
  analysisId: string;
  repoUrl: string;
  ref: string | null;
  sha: string;
  expiresAt: string;
}

export interface SavedViewState {
  selectedPath: string | null;
  expandedModules: string[];
  tab: WorkspaceTab;
  scopePaths: string[] | null;
  hideUnrelated: boolean;
  matchesOnly: boolean;
}

const DEFAULT_VIEW_STATE: SavedViewState = {
  selectedPath: null,
  expandedModules: [],
  tab: 'overview',
  scopePaths: null,
  hideUnrelated: false,
  matchesOnly: true,
};

function isRecentRepo(value: unknown): value is RecentRepo {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record['analysisId'] === 'string' &&
    typeof record['repoUrl'] === 'string' &&
    (record['ref'] === null || typeof record['ref'] === 'string') &&
    typeof record['sha'] === 'string' &&
    typeof record['expiresAt'] === 'string'
  );
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string');
}

function isWorkspaceTab(value: unknown): value is WorkspaceTab {
  return value === 'overview' || value === 'reading' || value === 'files';
}

/**
 * Loads non-expired recent repositories from localStorage, newest first.
 * Returns an empty list if localStorage is unavailable or unreadable.
 */
export function loadRecentRepos(now: number = Date.now()): RecentRepo[] {
  try {
    const raw = globalThis.localStorage?.getItem(RECENT_REPOS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(isRecentRepo)
      .filter(entry => {
        const expiresMs = Date.parse(entry.expiresAt);
        return Number.isNaN(expiresMs) || expiresMs > now;
      })
      .slice(0, MAX_RECENT_REPOS);
  } catch {
    return [];
  }
}

/**
 * Records a completed analysis in the recent repositories list in localStorage.
 */
export function saveRecentRepo(
  analysis: Pick<
    Analysis,
    'analysisId' | 'repoUrl' | 'ref' | 'sha' | 'status' | 'expiresAt'
  >,
  now: number = Date.now(),
): void {
  if (analysis.status !== 'completed') return;
  try {
    const existing = loadRecentRepos(now).filter(
      entry =>
        entry.analysisId !== analysis.analysisId &&
        !(entry.repoUrl === analysis.repoUrl && entry.sha === analysis.sha),
    );
    const next: RecentRepo[] = [
      {
        analysisId: analysis.analysisId,
        repoUrl: analysis.repoUrl,
        ref: analysis.ref,
        sha: analysis.sha,
        expiresAt: analysis.expiresAt,
      },
      ...existing,
    ].slice(0, MAX_RECENT_REPOS);
    globalThis.localStorage?.setItem(RECENT_REPOS_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable or full; ignore quietly.
  }
}

/**
 * Loads the saved workspace view state for a repository, or null if none is stored.
 */
export function loadViewState(repoUrl: string): SavedViewState | null {
  if (!repoUrl) return null;
  try {
    const raw = globalThis.localStorage?.getItem(VIEW_STATE_PREFIX + repoUrl);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const record = parsed as Record<string, unknown>;
    return {
      selectedPath:
        typeof record['selectedPath'] === 'string'
          ? record['selectedPath']
          : null,
      expandedModules: isStringArray(record['expandedModules'])
        ? record['expandedModules']
        : [],
      tab: isWorkspaceTab(record['tab']) ? record['tab'] : 'overview',
      scopePaths: isStringArray(record['scopePaths'])
        ? record['scopePaths']
        : null,
      hideUnrelated:
        typeof record['hideUnrelated'] === 'boolean'
          ? record['hideUnrelated']
          : false,
      matchesOnly:
        typeof record['matchesOnly'] === 'boolean'
          ? record['matchesOnly']
          : true,
    };
  } catch {
    return null;
  }
}

/**
 * Updates the saved workspace view state for a repository in localStorage.
 */
export function saveViewState(
  repoUrl: string,
  patch: Partial<SavedViewState>,
): void {
  if (!repoUrl) return;
  try {
    const current = loadViewState(repoUrl) ?? DEFAULT_VIEW_STATE;
    const next: SavedViewState = {...current, ...patch};
    globalThis.localStorage?.setItem(
      VIEW_STATE_PREFIX + repoUrl,
      JSON.stringify(next),
    );
  } catch {
    // Storage unavailable or full; ignore quietly.
  }
}

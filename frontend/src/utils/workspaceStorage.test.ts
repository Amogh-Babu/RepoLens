import {
  loadRecentRepos,
  loadViewState,
  MAX_RECENT_REPOS,
  saveRecentRepo,
  saveViewState,
} from './workspaceStorage.ts';

describe('workspaceStorage', () => {
  it('saves and loads non-expired recent repositories newest first', () => {
    const now = Date.parse('2026-11-16T00:00:00Z');
    saveRecentRepo(
      {
        analysisId: 'a-1',
        repoUrl: 'https://github.com/pallets/click',
        ref: 'main',
        sha: '1'.repeat(40),
        status: 'completed',
        expiresAt: '2026-11-17T00:00:00Z',
      },
      now,
    );
    saveRecentRepo(
      {
        analysisId: 'a-2',
        repoUrl: 'https://github.com/pallets/flask',
        ref: null,
        sha: '2'.repeat(40),
        status: 'completed',
        expiresAt: '2026-11-17T00:00:00Z',
      },
      now,
    );

    const recent = loadRecentRepos(now);
    expect(recent.map(entry => entry.analysisId)).toEqual(['a-2', 'a-1']);
  });

  it('deduplicates recent repositories by repoUrl and sha and drops expired ones', () => {
    const now = Date.parse('2026-11-16T12:00:00Z');
    saveRecentRepo(
      {
        analysisId: 'expired-1',
        repoUrl: 'https://github.com/old/repo',
        ref: null,
        sha: '0'.repeat(40),
        status: 'completed',
        expiresAt: '2026-11-16T13:00:00Z',
      },
      now,
    );
    saveRecentRepo(
      {
        analysisId: 'active-1',
        repoUrl: 'https://github.com/pallets/click',
        ref: null,
        sha: 'a'.repeat(40),
        status: 'completed',
        expiresAt: '2026-11-17T12:00:00Z',
      },
      now,
    );
    saveRecentRepo(
      {
        analysisId: 'active-2',
        repoUrl: 'https://github.com/pallets/click',
        ref: 'main',
        sha: 'a'.repeat(40),
        status: 'completed',
        expiresAt: '2026-11-17T12:00:00Z',
      },
      now,
    );

    const later = Date.parse('2026-11-16T14:00:00Z');
    expect(loadRecentRepos(later)).toEqual([
      {
        analysisId: 'active-2',
        repoUrl: 'https://github.com/pallets/click',
        ref: 'main',
        sha: 'a'.repeat(40),
        expiresAt: '2026-11-17T12:00:00Z',
      },
    ]);
  });

  it('caps the recent repositories list at MAX_RECENT_REPOS', () => {
    const now = Date.parse('2026-11-16T00:00:00Z');
    for (let i = 0; i < MAX_RECENT_REPOS + 3; i++) {
      saveRecentRepo(
        {
          analysisId: `a-${i}`,
          repoUrl: `https://github.com/org/repo-${i}`,
          ref: null,
          sha: String(i).padStart(40, '0'),
          status: 'completed',
          expiresAt: '2026-11-17T00:00:00Z',
        },
        now,
      );
    }
    expect(loadRecentRepos(now)).toHaveLength(MAX_RECENT_REPOS);
  });

  it('merges and restores workspace view state per repository', () => {
    const repo = 'https://github.com/repolens-demo/flask-auth';
    expect(loadViewState(repo)).toBeNull();

    saveViewState(repo, {
      selectedPath: 'app/auth/views.py',
      expandedModules: ['app/auth'],
    });
    saveViewState(repo, {
      tab: 'files',
      scopePaths: ['app/auth/views.py', 'app/auth/service.py'],
      hideUnrelated: true,
    });

    expect(loadViewState(repo)).toEqual({
      selectedPath: 'app/auth/views.py',
      expandedModules: ['app/auth'],
      tab: 'files',
      scopePaths: ['app/auth/views.py', 'app/auth/service.py'],
      hideUnrelated: true,
      matchesOnly: true,
    });
  });

  it('never throws when localStorage throws', () => {
    const getItem = vi
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('SecurityError');
      });
    const setItem = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new Error('QuotaExceededError');
      });

    expect(loadRecentRepos()).toEqual([]);
    expect(() =>
      saveRecentRepo({
        analysisId: 'a-1',
        repoUrl: 'https://github.com/pallets/click',
        ref: null,
        sha: '1'.repeat(40),
        status: 'completed',
        expiresAt: '2099-01-01T00:00:00Z',
      }),
    ).not.toThrow();
    expect(loadViewState('https://github.com/pallets/click')).toBeNull();
    expect(() =>
      saveViewState('https://github.com/pallets/click', {selectedPath: 'x.py'}),
    ).not.toThrow();

    getItem.mockRestore();
    setItem.mockRestore();
  });
});

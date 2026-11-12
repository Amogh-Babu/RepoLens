import type {ApiClient, RequestOptions} from '../client.ts';
import {ApiError} from '../errors.ts';
import {ANALYSIS_STAGES} from '../types.ts';
import type {
  Analysis,
  AnalysisStage,
  ApiErrorBody,
  DependencyGraph,
  FileDetail,
  RepositoryOverview,
  ModuleGroup,
  RankedFile,
  SearchMatch,
  SearchIntent,
  SearchRequest,
  SearchResponse,
  StartAnalysisRequest,
  StartAnalysisResponse,
} from '../types.ts';
import type {FixtureFile, FixtureRepo} from './fixtureRepo.ts';
import {FLASK_AUTH_REPO} from './fixtureRepo.ts';

const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
/** How long 'expires-soon' stays available after it completes. */
const SHORT_TTL_MS = 20_000;
const MAX_QUERY_LENGTH = 200;
const DEFAULT_PAGE_SIZE = 20;
const GITHUB_URL = /^https:\/\/github\.com\/([^/\s]+)\/([^/\s]+)$/;
const FULL_SHA = /^[0-9a-f]{40}$/i;

/**
 * Failures that occur partway through the pipeline, keyed by repository
 * name, so the progress and error screens can be exercised.
 */
const PIPELINE_FAILURES: Record<
  string,
  {stage: AnalysisStage; error: ApiErrorBody}
> = {
  'empty-repo': {
    stage: 'downloading',
    error: {
      code: 'REPO_EMPTY',
      message: 'This repository has no files, so there is nothing to analyze.',
      hint: null,
    },
  },
  'no-python': {
    stage: 'filtering',
    error: {
      code: 'NO_PYTHON_FILES',
      message: 'This repository has no Python files to analyze.',
      hint: 'This version of RepoLens supports only Python repositories.',
    },
  },
  'huge-repo': {
    stage: 'filtering',
    error: {
      code: 'TOO_MANY_FILES',
      message:
        'This repository has 4,812 Python files; the limit is 1,000 files.',
      hint: 'Try a smaller repository.',
    },
  },
  crash: {
    stage: 'parsing',
    error: {
      code: 'ANALYSIS_FAILED',
      message: 'Something went wrong while analyzing this repository.',
      hint: 'Try again in a moment.',
    },
  },
};

/** Failures returned immediately by POST /analyses, keyed by repo name. */
const START_FAILURES: Record<string, {status: number; error: ApiErrorBody}> = {
  'private-repo': {
    status: 404,
    error: {
      code: 'REPO_NOT_FOUND',
      message: 'This repository does not exist or is not public.',
      hint:
        'Check the spelling and that the repository is public. This version ' +
        'of RepoLens supports public GitHub repositories.',
    },
  },
  'rate-limited': {
    status: 429,
    error: {
      code: 'RATE_LIMITED',
      message: 'GitHub is limiting requests right now.',
      hint: 'Wait a minute, then try again.',
    },
  },
};

export interface MockApiClientOptions {
  /** Delay before every response. Defaults to 150 ms. */
  latencyMs?: number;
  /** Time each pipeline stage takes. Defaults to 600 ms. */
  stageDurationMs?: number;
  /** Clock, replaceable for tests. */
  now?: () => number;
  /** Repository served for every successful analysis. */
  repo?: FixtureRepo;
}

interface MockAnalysis {
  analysisId: string;
  repoUrl: string;
  repoName: string;
  ref: string | null;
  sha: string;
  startedAt: number;
  fromCache: boolean;
  cancelled: boolean;
}

/**
 * In-memory ApiClient that serves a fixture repository, for building the UI
 * before the backend exists. Every successful analysis serves the same files
 * under whatever repository URL was given.
 *
 * Special repository names (https://github.com/<anyone>/<name>) trigger the
 * error paths from the use cases:
 *
 * - private-repo: REPO_NOT_FOUND when starting
 * - rate-limited: RATE_LIMITED when starting
 * - empty-repo, no-python, huge-repo, crash: fail partway through analysis
 * - cached: completes immediately, marked as loaded from the cache
 * - expired-repo: completes, then every later request is ANALYSIS_EXPIRED
 * - expires-soon: completes, then expires 20 seconds later
 *
 * A ref named "missing-ref" fails with REF_NOT_FOUND.
 */
export class MockApiClient implements ApiClient {
  private readonly latencyMs: number;
  private readonly stageDurationMs: number;
  private readonly now: () => number;
  private readonly repo: FixtureRepo;
  private readonly analyses = new Map<string, MockAnalysis>();
  private nextId = 1;

  constructor(options: MockApiClientOptions = {}) {
    this.latencyMs = options.latencyMs ?? 150;
    this.stageDurationMs = options.stageDurationMs ?? 600;
    this.now = options.now ?? Date.now;
    this.repo = options.repo ?? FLASK_AUTH_REPO;
  }

  async startAnalysis(
    request: StartAnalysisRequest,
    options?: RequestOptions,
  ): Promise<StartAnalysisResponse> {
    await this.delay(options);

    const match = GITHUB_URL.exec(request.url);
    if (match === null) {
      throw new ApiError(
        'INVALID_URL',
        'This is not a GitHub repository URL.',
        'Use the format https://github.com/<owner>/<repo>.',
        400,
      );
    }
    const repoName = match[2] ?? '';
    const startFailure = START_FAILURES[repoName];
    if (startFailure !== undefined) {
      throw ApiError.fromBody(startFailure.error, startFailure.status);
    }
    const ref = request.ref?.trim() || null;
    if (ref === 'missing-ref') {
      throw new ApiError(
        'REF_NOT_FOUND',
        `The branch, tag or commit "${ref}" does not exist.`,
        'Leave the commit field empty to analyze the default branch.',
        404,
      );
    }

    const analysisId = `mock-${this.nextId++}`;
    const fromCache = repoName === 'cached';
    const analysis: MockAnalysis = {
      analysisId,
      repoUrl: request.url,
      repoName,
      ref,
      sha:
        ref !== null && FULL_SHA.test(ref) ? ref.toLowerCase() : this.repo.sha,
      startedAt: this.now(),
      fromCache,
      cancelled: false,
    };
    this.analyses.set(analysisId, analysis);
    return {
      analysisId,
      sha: analysis.sha,
      status: fromCache ? 'completed' : 'queued',
    };
  }

  async getAnalysis(
    analysisId: string,
    options?: RequestOptions,
  ): Promise<Analysis> {
    await this.delay(options);
    return this.describe(this.find(analysisId));
  }

  async cancelAnalysis(
    analysisId: string,
    options?: RequestOptions,
  ): Promise<void> {
    await this.delay(options);
    const analysis = this.find(analysisId);
    const status = this.describe(analysis).status;
    if (status === 'queued' || status === 'running') {
      analysis.cancelled = true;
    }
  }

  async getGraph(
    analysisId: string,
    options?: RequestOptions,
  ): Promise<DependencyGraph> {
    await this.delay(options);
    this.findCompleted(analysisId);

    const modules = new Map<string, ModuleGroup>();
    for (const file of this.repo.files) {
      const moduleId = moduleOf(file.path);
      let group = modules.get(moduleId);
      if (group === undefined) {
        group = {id: moduleId, name: moduleName(moduleId), filePaths: []};
        modules.set(moduleId, group);
      }
      group.filePaths.push(file.path);
    }

    return {
      modules: [...modules.values()],
      files: this.repo.files.map(file => ({
        path: file.path,
        module: moduleOf(file.path),
        parsed: file.parsed,
        lineCount: file.lineCount,
      })),
      edges: this.repo.files.flatMap(file =>
        file.imports.flatMap(imp =>
          imp.kind === 'internal' && imp.targetPath !== undefined
            ? [{source: file.path, target: imp.targetPath}]
            : [],
        ),
      ),
    };
  }

  async getOverview(
    analysisId: string,
    options?: RequestOptions,
  ): Promise<RepositoryOverview> {
    await this.delay(options);
    this.findCompleted(analysisId);

    const categories = this.repo.files.map(file => {
      const path = file.path.toLowerCase();
      const category =
        path.includes('/test') || path.startsWith('tests/') ? 'test' : 'source';
      return {path: file.path, category} as const;
    });
    const sourceFiles = this.repo.files.filter(
      file =>
        categories.find(item => item.path === file.path)?.category === 'source',
    );
    const entryPoints = sourceFiles
      .filter(file =>
        ['manage.py', 'main.py', 'app.py', '__main__.py'].includes(
          file.path.split('/').at(-1)?.toLowerCase() ?? '',
        ),
      )
      .map(file => ({
        path: file.path,
        reason: 'Conventional application or command entry-point filename.',
        summary:
          file.comments[0]?.text ?? `Defines ${file.symbols.length} symbols.`,
      }));
    const coreFiles = sourceFiles
      .map(file => ({
        path: file.path,
        score: this.importersOf(file.path).length,
        reason: `Imported by ${this.importersOf(file.path).length} analyzed files.`,
        summary:
          file.comments[0]?.text ?? `Defines ${file.symbols.length} symbols.`,
      }))
      .sort(
        (left, right) =>
          right.score - left.score || left.path.localeCompare(right.path),
      )
      .slice(0, 8);
    const modules = new Map<string, string[]>();
    for (const file of sourceFiles) {
      const module = moduleOf(file.path);
      const paths = modules.get(module) ?? [];
      paths.push(file.path);
      modules.set(module, paths);
    }
    const packages = [...modules].map(([id, paths]) => ({
      id,
      name: moduleName(id),
      fileCount: paths.length,
      layer: 0,
      cyclic: false,
    }));
    const areas = packages.map(module => ({
      id: module.id,
      name: module.name,
      files: modules.get(module.id) ?? [],
      summary: `${modules.get(module.id)?.length ?? 0} files in this module.`,
    }));
    const tourPaths: string[] = [];
    const visited = new Set<string>();
    const visit = (path: string) => {
      if (visited.has(path)) return;
      visited.add(path);
      const file = sourceFiles.find(candidate => candidate.path === path);
      for (const dependency of file?.imports ?? []) {
        if (
          dependency.kind === 'internal' &&
          dependency.targetPath !== undefined
        ) {
          visit(dependency.targetPath);
        }
      }
      tourPaths.push(path);
    };
    for (const entry of entryPoints) visit(entry.path);
    for (const file of coreFiles) {
      if (tourPaths.length >= 12) break;
      visit(file.path);
    }
    for (const file of sourceFiles) {
      if (tourPaths.length >= 12) break;
      visit(file.path);
    }

    return {
      entryPoints,
      coreFiles,
      architecture: {
        packages,
        edges: [],
        layers:
          packages.length > 0
            ? [
                {
                  depth: 0,
                  name: 'Foundations',
                  packages: packages.map(item => item.id),
                },
              ]
            : [],
        hasCycles: false,
      },
      areas,
      tour: tourPaths.map(path => ({
        path,
        reason: entryPoints.some(entry => entry.path === path)
          ? 'Start here: this is a conventional application entry point.'
          : 'Read this file to understand the repository structure.',
        summary:
          sourceFiles.find(file => file.path === path)?.comments[0]?.text ?? '',
      })),
      categories,
    };
  }

  async getFile(
    analysisId: string,
    path: string,
    options?: RequestOptions,
  ): Promise<FileDetail> {
    await this.delay(options);
    const analysis = this.findCompleted(analysisId);
    const file = this.repo.files.find(f => f.path === path);
    if (file === undefined) {
      throw new ApiError(
        'FILE_NOT_FOUND',
        `"${path}" is not part of this analysis.`,
        null,
        404,
      );
    }

    return {
      path: file.path,
      module: moduleOf(file.path),
      parsed: file.parsed,
      lineCount: file.lineCount,
      symbols: file.symbols.map(symbol => ({...symbol})),
      imports: file.imports.map(imp => ({
        rawName: imp.rawName,
        kind: imp.kind,
        targetPath: imp.targetPath ?? null,
        targetPackage: imp.targetPackage ?? null,
      })),
      importedBy: this.importersOf(file.path),
      sourceUrl: `${analysis.repoUrl}/blob/${analysis.sha}/${file.path}`,
    };
  }

  async search(
    analysisId: string,
    request: SearchRequest,
    options?: RequestOptions,
  ): Promise<SearchResponse> {
    await this.delay(options);
    this.findCompleted(analysisId);

    const query = request.q.trim();
    if (query === '' || query.length > MAX_QUERY_LENGTH) {
      throw new ApiError(
        'INVALID_QUERY',
        query === ''
          ? 'Enter a keyword to search for.'
          : `Searches are limited to ${MAX_QUERY_LENGTH} characters.`,
        null,
        400,
      );
    }

    const ranked = rankFiles(
      this.repo.files,
      query.toLowerCase().split(/\s+/),
      request.intent,
    );
    const offset = request.offset ?? 0;
    const limit = request.limit ?? DEFAULT_PAGE_SIZE;
    return {
      query,
      total: ranked.length,
      results: ranked.slice(offset, offset + limit),
      matchedPaths: ranked.map(file => file.path),
    };
  }

  /** Waits for the simulated latency, honoring the caller's signal. */
  private delay(options: RequestOptions = {}): Promise<void> {
    const {signal} = options;
    return new Promise((resolve, reject) => {
      const aborted = () =>
        reject(new ApiError('ABORTED', 'The request was cancelled.'));
      if (signal?.aborted) {
        aborted();
        return;
      }
      const timer = setTimeout(() => {
        signal?.removeEventListener('abort', onAbort);
        resolve();
      }, this.latencyMs);
      const onAbort = () => {
        clearTimeout(timer);
        aborted();
      };
      signal?.addEventListener('abort', onAbort, {once: true});
    });
  }

  private find(analysisId: string): MockAnalysis {
    const analysis = this.analyses.get(analysisId);
    if (analysis === undefined) {
      throw new ApiError(
        'ANALYSIS_NOT_FOUND',
        'This analysis does not exist.',
        'Analyze the repository again.',
        404,
      );
    }
    return analysis;
  }

  /** Finds an analysis that can serve graph, file and search requests. */
  private findCompleted(analysisId: string): MockAnalysis {
    const analysis = this.find(analysisId);
    if (
      analysis.repoName === 'expired-repo' ||
      this.now() >= this.expiresAt(analysis)
    ) {
      throw new ApiError(
        'ANALYSIS_EXPIRED',
        'This analysis is no longer available.',
        'Re-analyze the repository to continue.',
        410,
      );
    }
    if (this.describe(analysis).status !== 'completed') {
      throw new ApiError(
        'ANALYSIS_NOT_READY',
        'This analysis has not finished yet.',
        null,
        409,
      );
    }
    return analysis;
  }

  private expiresAt(analysis: MockAnalysis): number {
    return analysis.repoName === 'expires-soon'
      ? analysis.startedAt +
          this.stageDurationMs * ANALYSIS_STAGES.length +
          SHORT_TTL_MS
      : analysis.startedAt + CACHE_TTL_MS;
  }

  /** Computes the current status of an analysis from the elapsed time. */
  private describe(analysis: MockAnalysis): Analysis {
    const base = {
      analysisId: analysis.analysisId,
      repoUrl: analysis.repoUrl,
      ref: analysis.ref,
      sha: analysis.sha,
      fromCache: analysis.fromCache,
      createdAt: new Date(analysis.startedAt).toISOString(),
      expiresAt: new Date(this.expiresAt(analysis)).toISOString(),
    };
    if (analysis.cancelled) {
      return {
        ...base,
        status: 'cancelled',
        stage: null,
        summary: null,
        error: null,
      };
    }

    const stageIndex = analysis.fromCache
      ? ANALYSIS_STAGES.length
      : Math.floor((this.now() - analysis.startedAt) / this.stageDurationMs);

    const failure = PIPELINE_FAILURES[analysis.repoName];
    if (
      failure !== undefined &&
      stageIndex > ANALYSIS_STAGES.indexOf(failure.stage)
    ) {
      return {
        ...base,
        status: 'failed',
        stage: null,
        summary: null,
        error: failure.error,
      };
    }

    const stage = ANALYSIS_STAGES[stageIndex];
    if (stage !== undefined) {
      return {
        ...base,
        status: stageIndex === 0 ? 'queued' : 'running',
        stage,
        summary: null,
        error: null,
      };
    }

    return {
      ...base,
      status: 'completed',
      stage: null,
      summary: {
        filesAnalyzed: this.repo.files.length,
        filesExcluded: this.repo.filesExcluded,
        filesUnparsed: this.repo.files.filter(f => !f.parsed).length,
      },
      error: null,
    };
  }

  private importersOf(path: string): string[] {
    return this.repo.files
      .filter(file => file.imports.some(imp => imp.targetPath === path))
      .map(file => file.path);
  }
}

/** Directory of a file, used as its module id. "." for root files. */
function moduleOf(path: string): string {
  const slash = path.lastIndexOf('/');
  return slash === -1 ? '.' : path.slice(0, slash);
}

function moduleName(moduleId: string): string {
  return moduleId === '.' ? '(root)' : (moduleId.split('/').pop() ?? moduleId);
}

/**
 * A simple stand-in for the backend's ranking: files matching more terms and
 * more evidence rank higher, and a file that other matching files import is
 * moved ahead of them, so the list reads foundations first.
 */
function rankFiles(
  files: FixtureFile[],
  terms: string[],
  intent?: SearchIntent,
): RankedFile[] {
  const candidates = files.flatMap(file => {
    const matches = matchFile(file, terms);
    if (matches.length === 0) return [];
    const termsMatched = terms.filter(term =>
      matches.some(m => m.text.toLowerCase().includes(term)),
    ).length;
    const evidence = matches.reduce(
      (sum, m) => sum + (m.kind === 'symbol' || m.kind === 'filename' ? 3 : 1),
      0,
    );
    return [{file, matches, score: termsMatched * 10 + evidence}];
  });

  const matchedPaths = new Set(candidates.map(c => c.file.path));
  const scored = candidates.map(candidate => {
    const importers = files.filter(
      other =>
        matchedPaths.has(other.path) &&
        other.imports.some(imp => imp.targetPath === candidate.file.path),
    ).length;
    const parts = candidate.file.path.toLowerCase().split(/[/_.-]+/);
    const isTest = parts.some(part =>
      ['test', 'tests', 'spec', 'specs', 'example', 'examples'].includes(part),
    );
    const isConfig = parts.some(part =>
      [
        'config',
        'configuration',
        'settings',
        'deploy',
        'deployment',
        'dockerfile',
        'compose',
        'helm',
        'env',
      ].includes(part),
    );
    const prioritized =
      intent === 'tests'
        ? isTest
        : intent === 'configuration'
          ? isConfig && !isTest
          : intent === 'implementation' && !isTest && !isConfig;
    return {
      ...candidate,
      importers,
      prioritized,
      score: (candidate.score + importers * 5) * (prioritized ? 2 : 1),
    };
  });

  scored.sort(
    (a, b) => b.score - a.score || a.file.path.localeCompare(b.file.path),
  );
  const order = scored.map(entry => entry.file);
  return scored.map((entry, index) => ({
    position: index + 1,
    path: entry.file.path,
    score: entry.score,
    reason:
      buildReason(entry.matches, entry.importers) +
      (entry.prioritized ? ` Prioritized for ${intent}.` : ''),
    orderReason: buildOrderReason(order, index),
    matches: entry.matches,
  }));
}

/** Same wording as the backend's order reasons, from the mock's order. */
function buildOrderReason(order: FixtureFile[], index: number): string {
  const file = order[index];
  if (file === undefined) return '';
  const imports = (other: FixtureFile, target: FixtureFile) =>
    other.imports.some(imp => imp.targetPath === target.path);
  const before = order.slice(0, index).filter(other => imports(file, other));
  const after = order.slice(index + 1).filter(other => imports(other, file));
  const parts: string[] = [];
  if (before.length > 0) {
    parts.push(`Comes after ${nameFiles(before)}, which it imports`);
  }
  if (after.length > 0) {
    const verb = after.length === 1 ? 'imports' : 'import';
    parts.push(`comes before ${nameFiles(after)}, which ${verb} it`);
  }
  if (parts.length === 0) {
    return (
      'Does not import or get imported by the other results, ' +
      'so it is placed by how strongly it matches.'
    );
  }
  const sentence = parts.join('; ');
  return `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`;
}

function nameFiles(files: FixtureFile[]): string {
  const [first, second] = files;
  if (files.length === 1) return first?.path ?? '';
  if (files.length === 2) return `${first?.path} and ${second?.path}`;
  return `${first?.path}, ${second?.path} and ${files.length - 2} more`;
}

function matchFile(file: FixtureFile, terms: string[]): SearchMatch[] {
  const hits = (text: string) =>
    terms.some(term => text.toLowerCase().includes(term));
  const matches: SearchMatch[] = [];
  if (hits(file.path)) {
    matches.push({kind: 'filename', text: file.path, line: null});
  }
  for (const symbol of file.symbols) {
    if (hits(symbol.name)) {
      matches.push({kind: 'symbol', text: symbol.name, line: symbol.line});
    }
  }
  for (const imp of file.imports) {
    if (hits(imp.rawName)) {
      matches.push({kind: 'import', text: imp.rawName, line: null});
    }
  }
  for (const comment of file.comments) {
    if (hits(comment.text)) {
      matches.push({kind: 'comment', text: comment.text, line: comment.line});
    }
  }
  return matches;
}

function buildReason(matches: SearchMatch[], importers: number): string {
  const symbols = matches.filter(m => m.kind === 'symbol').map(m => m.text);
  let reason: string;
  if (symbols.length > 0) {
    reason = `Defines ${symbols.slice(0, 3).join(', ')}`;
  } else if (matches.some(m => m.kind === 'filename')) {
    reason = 'File name matches';
  } else if (matches.some(m => m.kind === 'import')) {
    reason = `Imports ${matches.find(m => m.kind === 'import')?.text}`;
  } else {
    reason = 'Mentioned in a comment';
  }
  if (importers > 0) {
    reason += `; imported by ${importers} other matching file${importers === 1 ? '' : 's'}`;
  }
  return reason;
}

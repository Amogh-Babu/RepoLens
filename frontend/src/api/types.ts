/**
 * Types for the RepoLens REST API, as the frontend expects it.
 *
 * The living document fixes the endpoints and the error shape but not the
 * response bodies. Everything below the endpoint level is a proposal until
 * the backend's OpenAPI schema (the source of truth) agrees with it. JSON
 * field names are camelCase, matching `{analysisId, sha, status}` in the doc.
 */

/** Lifecycle of one analysis. */
export type AnalysisStatus =
  'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

/** Pipeline stage of a running analysis, in the order they run. */
export type AnalysisStage =
  | 'resolving'
  | 'downloading'
  | 'filtering'
  | 'parsing'
  | 'classifying'
  | 'indexing'
  | 'storing';

/** Every pipeline stage, in order. Useful for progress displays. */
export const ANALYSIS_STAGES: readonly AnalysisStage[] = [
  'resolving',
  'downloading',
  'filtering',
  'parsing',
  'classifying',
  'indexing',
  'storing',
];

/** Body of every error response: `{code, message, hint}`. */
export interface ApiErrorBody {
  code: string;
  message: string;
  /** Suggested next step for the user, if any. */
  hint: string | null;
}

/** POST /analyses request body. */
export interface StartAnalysisRequest {
  /** Normalized repository URL, e.g. https://github.com/owner/repo. */
  url: string;
  /** Commit SHA, branch or tag. Omitted means the default branch. */
  ref?: string;
}

/** POST /analyses response body. */
export interface StartAnalysisResponse {
  analysisId: string;
  /** Resolved commit SHA. */
  sha: string;
  status: AnalysisStatus;
}

/** File counts shown in the summary bar. */
export interface AnalysisSummary {
  filesAnalyzed: number;
  filesExcluded: number;
  filesUnparsed: number;
}

/** GET /analyses/{id} response body. */
export interface Analysis {
  analysisId: string;
  /** Normalized repository URL, e.g. https://github.com/owner/repo. */
  repoUrl: string;
  /** Branch or tag the user asked for, or null for the default branch. */
  ref: string | null;
  sha: string;
  status: AnalysisStatus;
  /** Current stage while queued or running; null otherwise. */
  stage: AnalysisStage | null;
  /** Present once the analysis has completed. */
  summary: AnalysisSummary | null;
  /** True when the result was loaded from the cache. */
  fromCache: boolean;
  /** ISO 8601 timestamps. */
  createdAt: string;
  expiresAt: string;
  /** Present when status is 'failed'. */
  error: ApiErrorBody | null;
}

/** A group of files shown as one collapsible node on the map. */
export interface ModuleGroup {
  /** Directory path of the module, e.g. "app/auth". "." for the root. */
  id: string;
  /** Display name, e.g. "auth". */
  name: string;
  /** Paths of the files in this module. */
  filePaths: string[];
}

/** A file node on the dependency map. */
export interface FileNode {
  /** Repository-relative path; unique within an analysis. */
  path: string;
  /** Id of the module group this file belongs to. */
  module: string;
  /** False when the file could not be parsed (e.g. a syntax error). */
  parsed: boolean;
  lineCount: number;
}

/** An internal import: `source` imports `target`. Both are file paths. */
export interface ImportEdge {
  source: string;
  target: string;
}

/** GET /analyses/{id}/graph response body. */
export interface DependencyGraph {
  modules: ModuleGroup[];
  files: FileNode[];
  edges: ImportEdge[];
}

export interface OverviewFile {
  path: string;
  reason: string;
  summary: string;
  /** Only verified AI descriptions are marked 'ai'. */
  summarySource?: 'static' | 'ai';
  score?: number;
}

export interface OverviewPackage {
  id: string;
  name: string;
  fileCount: number;
  layer: number;
  cyclic: boolean;
}

export interface OverviewArchitecture {
  packages: OverviewPackage[];
  edges: Array<{source: string; target: string; count: number}>;
  layers: Array<{depth: number; name: string; packages: string[]}>;
  hasCycles: boolean;
}

export interface OverviewArea {
  id: string;
  name: string;
  files: string[];
  summary: string;
}

export interface OverviewCategory {
  path: string;
  category:
    'source' | 'test' | 'tool' | 'docs' | 'example' | 'config' | 'migration';
}

/** GET /analyses/{id}/overview response body. */
export interface RepositoryOverview {
  entryPoints: OverviewFile[];
  coreFiles: OverviewFile[];
  architecture: OverviewArchitecture;
  areas: OverviewArea[];
  tour: OverviewFile[];
  categories: OverviewCategory[];
}

export type SymbolKind = 'function' | 'class' | 'variable';

export interface SymbolInfo {
  name: string;
  kind: SymbolKind;
  /** 1-based line of the definition. */
  line: number;
}

export type ImportKind = 'internal' | 'external' | 'unresolved';

export interface ImportInfo {
  /** The import as written, e.g. "app.auth.service" or "flask". */
  rawName: string;
  kind: ImportKind;
  /** Path of the imported file, for internal imports. */
  targetPath: string | null;
  /** Top-level package name, for external imports. */
  targetPackage: string | null;
}

/** GET /analyses/{id}/files/{path} response body. */
export interface FileDetail {
  path: string;
  module: string;
  parsed: boolean;
  lineCount: number;
  symbols: SymbolInfo[];
  imports: ImportInfo[];
  /** Paths of the files that import this one. */
  importedBy: string[];
  /** https://github.com/<owner>/<repo>/blob/<sha>/<path> */
  sourceUrl: string;
}

export type MatchKind =
  'filename' | 'symbol' | 'import' | 'comment' | 'semantic';

/** One piece of evidence for why a file matched a query. */
export interface SearchMatch {
  kind: MatchKind;
  text: string;
  /** 1-based line, or null for filename matches. */
  line: number | null;
}

/** One entry in the ranked reading list. */
export interface RankedFile {
  /** 1-based position in the reading order. */
  position: number;
  path: string;
  score: number;
  /** One-line reason citing evidence: why the file matched. */
  reason: string;
  /**
   * Why the file sits at this position: which matching files it comes
   * after (it imports them) or before (they import it).
   */
  orderReason: string;
  /** Every match in this file, for the expanded reason view. */
  matches: SearchMatch[];
}

/** GET /analyses/{id}/search query parameters. */
export type SearchIntent = 'implementation' | 'configuration' | 'tests';

export interface SearchRequest {
  q: string;
  intent?: SearchIntent;
  /** Page size. Defaults to 20 on the backend. */
  limit?: number;
  /** Number of results to skip, for "Show more". */
  offset?: number;
}

/** GET /analyses/{id}/search response body. */
export interface SearchResponse {
  query: string;
  /** Total number of matching files, across all pages. */
  total: number;
  results: RankedFile[];
  matchedPaths?: string[];
}

/** Today's AI usage, as reported by GET /ai/status. */
export interface AiUsage {
  day: string;
  modelCalls: number;
  inputTokens: number;
  outputTokens: number;
  cacheHits: number;
  cacheMisses: number;
  cacheHitRate: number | null;
  validationFailures: number;
  providerFailures: number;
  averageLatencyMs: number | null;
  /** Null unless the backend was given token prices. */
  estimatedCostUsd: number | null;
}

/** GET /ai/status response body. */
export interface AiStatus {
  enabled: boolean;
  /** Who receives the source when a summary is generated, e.g. "OpenAI". */
  provider: string | null;
  model: string | null;
  /** What generating a summary sends where; shown before generating. */
  notice: string | null;
  /**
   * What generating a search overview sends where; shown before
   * generating. Absent on backends without search overviews.
   */
  searchNotice?: string | null;
  dailyCallLimit: number | null;
  usage: AiUsage | null;
}

export type SummaryCoverage = 'complete' | 'partial';

export interface SummaryKeySymbol {
  /** Top-level name, or `Owner.member` for a method or attribute. */
  name: string;
  kind: 'function' | 'class' | 'variable' | 'method' | 'attribute';
  description: string;
  line: number;
  /** GitHub link to the line at the analyzed commit. */
  url: string;
}

export interface SummaryDependency {
  path: string;
  relationship: 'imports' | 'importedBy';
  description: string;
}

export interface SummarySideEffect {
  kind:
    | 'database'
    | 'filesystem'
    | 'network'
    | 'subprocess'
    | 'environment'
    | 'other';
  description: string;
  startLine: number;
  endLine: number;
  url: string;
}

export interface SummaryEvidence {
  startLine: number;
  endLine: number;
  description: string;
  /** GitHub link to the line range at the analyzed commit. */
  url: string;
}

/** A verified AI summary. Every field is plain text, never HTML. */
export interface CodeSummary {
  summary: string;
  purpose: string;
  responsibilities: string[];
  keySymbols: SummaryKeySymbol[];
  dependencies: SummaryDependency[];
  sideEffects: SummarySideEffect[];
  uncertainties: string[];
  evidence: SummaryEvidence[];
  coverage: SummaryCoverage;
}

/** Provenance of a summary, filled in by RepoLens, not by the model. */
export interface SummaryMetadata {
  model: string;
  promptVersion: string;
  schemaVersion: string;
  sourceHash: string;
  /** ISO 8601. */
  generatedAt: string;
  /** True when served from the cache instead of generated now. */
  cached: boolean;
  cacheStatus: 'hit' | 'miss' | 'regenerated';
  coverage: SummaryCoverage;
  /** 1-based inclusive [start, end] line ranges the model was shown. */
  inspectedLines: Array<[number, number]>;
  lineCount: number;
  sourceUrl: string;
}

/** GET and POST /analyses/{id}/ai-summaries/{path} response body. */
export interface FileSummary {
  analysisId: string;
  path: string;
  sha: string;
  status: 'notGenerated' | 'completed';
  summary: CodeSummary | null;
  metadata: SummaryMetadata | null;
}

/** One file the AI search overview points the reader to. */
export interface SearchOverviewStep {
  path: string;
  /** Why to read this file, in plain text. */
  reason: string;
}

/** A verified AI overview of a search. Every field is plain text, never HTML. */
export interface SearchOverview {
  summary: string;
  startHere: SearchOverviewStep;
  readNext: SearchOverviewStep[];
  uncertainties: string[];
}

/** Provenance of a search overview, filled in by RepoLens, not the model. */
export interface SearchOverviewMetadata {
  model: string;
  promptVersion: string;
  schemaVersion: string;
  /** ISO 8601. */
  generatedAt: string;
  /** True when served from the cache instead of generated now. */
  cached: boolean;
  cacheStatus: 'hit' | 'miss' | 'regenerated';
  /** Paths whose cached AI file summaries the model was shown. */
  usedFileSummaries: string[];
}

/** GET and POST /analyses/{id}/ai-search-overview query parameters. */
export interface SearchOverviewRequest {
  q: string;
  intent?: SearchIntent | null;
}

/** GET and POST /analyses/{id}/ai-search-overview response body. */
export interface SearchOverviewResponse {
  analysisId: string;
  query: string;
  intent: SearchIntent | null;
  /** 'noResults' when the query matches no files, so there is nothing to summarize. */
  status: 'notGenerated' | 'completed' | 'noResults';
  overview: SearchOverview | null;
  metadata: SearchOverviewMetadata | null;
}

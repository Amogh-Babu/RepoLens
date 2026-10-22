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
  | 'storing';

/** Every pipeline stage, in order. Useful for progress displays. */
export const ANALYSIS_STAGES: readonly AnalysisStage[] = [
  'resolving',
  'downloading',
  'filtering',
  'parsing',
  'classifying',
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

export type MatchKind = 'filename' | 'symbol' | 'import' | 'comment';

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
  /** One-line reason citing evidence. */
  reason: string;
  /** Every match in this file, for the expanded reason view. */
  matches: SearchMatch[];
}

/** GET /analyses/{id}/search query parameters. */
export interface SearchRequest {
  q: string;
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
}

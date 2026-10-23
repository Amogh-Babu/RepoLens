/**
 * Checks and normalizes what the user typed into the repository form, before
 * anything is sent to the backend (Use Case 1, step 2; Use Case 5, 2a-2b).
 */

/** Why the input was rejected. */
export type RepoInputErrorKind =
  'empty' | 'invalid-format' | 'unsupported-host' | 'invalid-ref';

export interface RepoInputError {
  kind: RepoInputErrorKind;
  message: string;
}

/** A repository the backend can be asked to analyze. */
export interface RepoTarget {
  /** Normalized URL: https://github.com/<owner>/<repo>. */
  url: string;
  owner: string;
  repo: string;
  /** Branch, tag or commit, or null for the default branch. */
  ref: string | null;
}

export type RepoInputResult =
  {ok: true; target: RepoTarget} | {ok: false; error: RepoInputError};

export const EXAMPLE_REPO_URL = 'https://github.com/owner/repo';

const MAX_REF_LENGTH = 255;

// GitHub's own rules: owners are letters, digits and single hyphens; repos
// are letters, digits, '.', '-' and '_'.
const OWNER = /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/;
const REPO = /^[A-Za-z0-9._-]{1,100}$/;

/** A subset of git's ref name rules, enough to catch typos. */
const INVALID_REF = /[\s~^:?*[\\]|\.\.|@\{|^[/.]|[/.]$|\.lock$|\/\//;

const GITHUB_HOSTS = new Set(['github.com', 'www.github.com']);

/** Hosts we name in the error, so users know support is planned. */
const OTHER_GIT_HOSTS: Record<string, string> = {
  'gitlab.com': 'GitLab',
  'bitbucket.org': 'Bitbucket',
  'codeberg.org': 'Codeberg',
};

/**
 * Parses the URL and optional ref fields.
 *
 * Accepts a trailing slash, a `.git` suffix, a missing `https://`, and
 * `/tree/<branch>` or `/commit/<sha>` paths; the branch or commit from the
 * path is used when the ref field is empty. Other extra path segments (for
 * example `/issues`) are dropped.
 */
export function parseRepoInput(rawUrl: string, rawRef = ''): RepoInputResult {
  const trimmed = rawUrl.trim();
  if (trimmed === '') {
    return failure('empty', 'Enter a GitHub repository URL.');
  }

  const url = toUrl(trimmed);
  if (url === null || !['http:', 'https:'].includes(url.protocol)) {
    return invalidFormat();
  }

  const host = url.hostname.toLowerCase();
  if (!GITHUB_HOSTS.has(host)) {
    const hostName = OTHER_GIT_HOSTS[host];
    return failure(
      'unsupported-host',
      hostName === undefined
        ? 'RepoLens currently supports only public repositories on ' +
            'github.com.'
        : `RepoLens currently supports only public repositories on ` +
            `github.com. Support for other Git hosts such as ${hostName} ` +
            `is planned.`,
    );
  }

  const segments = url.pathname.split('/').filter(s => s !== '');
  const [owner, rawRepo, kind, ...rest] = segments.map(decodeSegment);
  const repo = rawRepo?.replace(/\.git$/i, '');
  if (
    owner === undefined ||
    repo === undefined ||
    !OWNER.test(owner) ||
    !REPO.test(repo) ||
    repo === '.' ||
    repo === '..'
  ) {
    return invalidFormat();
  }

  let ref: string | null = rawRef.trim() || null;
  if (ref === null && (kind === 'tree' || kind === 'commit')) {
    ref = rest.join('/') || null;
  }
  if (ref !== null && (ref.length > MAX_REF_LENGTH || INVALID_REF.test(ref))) {
    return failure(
      'invalid-ref',
      `"${truncate(ref)}" is not a valid branch, tag or commit name.`,
    );
  }

  return {
    ok: true,
    target: {url: `https://github.com/${owner}/${repo}`, owner, repo, ref},
  };
}

function toUrl(text: string): URL | null {
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(text)
    ? text
    : `https://${text}`;
  try {
    return new URL(withScheme);
  } catch {
    return null;
  }
}

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function truncate(text: string): string {
  return text.length > 40 ? `${text.slice(0, 40)}…` : text;
}

function invalidFormat(): RepoInputResult {
  return failure(
    'invalid-format',
    `Enter a GitHub repository URL, for example ${EXAMPLE_REPO_URL}.`,
  );
}

function failure(kind: RepoInputErrorKind, message: string): RepoInputResult {
  return {ok: false, error: {kind, message}};
}

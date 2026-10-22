import {parseRepoInput} from './repoInput.ts';

function target(url: string, ref = '') {
  const result = parseRepoInput(url, ref);
  if (!result.ok) {
    throw new Error(`Expected ${url} to be valid: ${result.error.message}`);
  }
  return result.target;
}

function errorKind(url: string, ref = '') {
  const result = parseRepoInput(url, ref);
  return result.ok ? null : result.error.kind;
}

describe('parseRepoInput', () => {
  it.each([
    'https://github.com/pallets/flask',
    'https://github.com/pallets/flask/',
    'https://github.com/pallets/flask.git',
    'http://github.com/pallets/flask',
    'https://www.github.com/pallets/flask',
    'github.com/pallets/flask',
    '  https://github.com/pallets/flask  ',
    'https://github.com/pallets/flask/issues/42',
    'https://github.com/pallets/flask?tab=readme#install',
  ])('normalizes %s to the base repository URL', url => {
    expect(target(url)).toEqual({
      url: 'https://github.com/pallets/flask',
      owner: 'pallets',
      repo: 'flask',
      ref: null,
    });
  });

  it('keeps dots, dashes and underscores in repository names', () => {
    expect(target('https://github.com/my-org/my_repo.v2.git').url).toBe(
      'https://github.com/my-org/my_repo.v2',
    );
  });

  it('uses the branch from a /tree/ path, including slashes', () => {
    expect(target('https://github.com/o/r/tree/feature/login').ref).toBe(
      'feature/login',
    );
  });

  it('uses the SHA from a /commit/ path', () => {
    const sha = '3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f';
    expect(target(`https://github.com/o/r/commit/${sha}`).ref).toBe(sha);
  });

  it('prefers the ref field over a branch in the URL', () => {
    expect(target('https://github.com/o/r/tree/dev', ' v1.2.0 ').ref).toBe(
      'v1.2.0',
    );
  });

  it('treats an empty ref as the default branch', () => {
    expect(target('https://github.com/o/r', '   ').ref).toBeNull();
  });

  it('rejects empty input', () => {
    expect(errorKind('   ')).toBe('empty');
  });

  it.each([
    'not a url',
    'https://github.com',
    'https://github.com/pallets',
    'https://github.com/-bad-owner/repo',
    'https://github.com/owner/bad repo',
    'https://github.com/owner/..',
    'ftp://github.com/o/r',
    'javascript:alert(1)',
  ])('rejects %s as an invalid format', url => {
    expect(errorKind(url)).toBe('invalid-format');
  });

  it('names the host when the URL is on another known Git host', () => {
    const result = parseRepoInput('https://gitlab.com/group/project');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe('unsupported-host');
      expect(result.error.message).toMatch(/GitLab is planned/);
    }
  });

  it('rejects any other host', () => {
    expect(errorKind('https://example.com/o/r')).toBe('unsupported-host');
  });

  it.each(['has space', 'a..b', 'ends.lock', '/leading', 'x'.repeat(256)])(
    'rejects the invalid ref %s',
    ref => {
      expect(errorKind('https://github.com/o/r', ref)).toBe('invalid-ref');
    },
  );
});

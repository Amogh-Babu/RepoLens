import {checkQuery, MAX_QUERY_LENGTH} from './searchQuery.ts';

describe('checkQuery', () => {
  it('trims the query', () => {
    expect(checkQuery('  login user  ')).toEqual({
      ok: true,
      query: 'login user',
    });
  });

  it.each(['', '   ', '\t\n'])('rejects an empty query (%j)', raw => {
    expect(checkQuery(raw)).toEqual({
      ok: false,
      message: 'Enter a keyword to search for.',
    });
  });

  it('accepts a query at the limit and rejects one over it', () => {
    expect(checkQuery('x'.repeat(MAX_QUERY_LENGTH)).ok).toBe(true);

    const result = checkQuery('x'.repeat(MAX_QUERY_LENGTH + 1));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.message).toMatch(
        /limited to 200 characters; this one has 201/,
      );
    }
  });

  it('measures the length after trimming', () => {
    expect(checkQuery(`  ${'x'.repeat(MAX_QUERY_LENGTH)}  `).ok).toBe(true);
  });
});

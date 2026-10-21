/** Longest query the backend accepts (Use Case 2). */
export const MAX_QUERY_LENGTH = 200;

export type QueryCheck =
  {ok: true; query: string} | {ok: false; message: string};

/**
 * Trims a search query and rejects one that is empty or too long, so no
 * request is sent for it (Use Case 2 exceptions).
 */
export function checkQuery(raw: string): QueryCheck {
  const query = raw.trim();
  if (query === '') {
    return {ok: false, message: 'Enter a keyword to search for.'};
  }
  if (query.length > MAX_QUERY_LENGTH) {
    return {
      ok: false,
      message: `Searches are limited to ${MAX_QUERY_LENGTH} characters; this one has ${query.length}.`,
    };
  }
  return {ok: true, query};
}

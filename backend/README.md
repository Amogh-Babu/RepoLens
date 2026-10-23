# Backend

## Search service

The Week 3 search component is implemented in `repolens.search`. It reads
normalized `SearchDocument` records through the `SearchIndex` protocol, keyed
by `analysis_id`, and returns a paginated `SearchPage`. This isolates ranking
from the graph database and HTTP framework. The record fields (`path`,
`symbols`, `references`, and `comments`) are language-neutral; an analyzer or
graph adapter for another language can map its extracted data into the same
contract.

```python
from repolens.search import SearchDocument, SearchService

class GraphSearchIndex:
	def get_search_documents(self, analysis_id: str):
		# Adapt the graph store's file, symbol, reference, and comment rows.
		...

results = SearchService(GraphSearchIndex()).search("analysis-id", "login")
for result in results.results:
	print(result.path, result.reason)
```

Queries are case-insensitive, split into distinct word terms, and limited to
200 characters. Whitespace-only queries raise `QueryValidationError`. The
default page contains 20 results; `offset` and `limit` support subsequent
pages, with a maximum page size of 100. Matches are found in filenames,
symbols, references (including language-specific imports), and comments. The
baseline score weights those fields 8, 6, 4, and 2 points per matched term,
respectively, adds 3 points per distinct matched query term, and adds 1.5
points for each other matching file that depends on the candidate. Results
sort by descending score, then by case-insensitive path. Each result's
single-line reason names up to two matching values and notes matching
dependents. The page reports the total match count and whether more results
are available.

Run the backend unit tests from the repository root with:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
```

The HTTP search route and production graph-store adapter are not yet
implemented. The API route should validate the analysis ID and query, call
`SearchService.search(analysis_id, query, offset, limit)`, and serialize the
`SearchPage`. The graph-store adapter should implement `SearchIndex` without
exposing database-specific records to the search service.

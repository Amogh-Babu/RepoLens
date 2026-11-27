import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {ApiClientContext} from '../api/apiClientContext.ts';
import type {ApiClient} from '../api/client.ts';
import type {
  AiStatus,
  RankedFile,
  SearchOverviewResponse,
} from '../api/types.ts';
import type {SearchState} from '../state/analysisStore.ts';
import {ReadingList} from './ReadingList.tsx';

const SERVICE: RankedFile = {
  position: 1,
  path: 'app/auth/service.py',
  score: 40,
  reason: 'Defines login_user; imported by 2 other matching files',
  orderReason: 'Comes before app/auth/views.py, which imports it.',
  matches: [
    {kind: 'symbol', text: 'login_user', line: 22},
    {kind: 'filename', text: 'app/auth/service.py', line: null},
  ],
};
const VIEWS: RankedFile = {
  position: 2,
  path: 'app/auth/views.py',
  score: 20,
  reason: 'Defines login',
  orderReason: 'Comes after app/auth/service.py, which it imports.',
  matches: [{kind: 'symbol', text: 'login', line: 11}],
};

function searchState(overrides: Partial<SearchState> = {}): SearchState {
  return {
    query: 'login',
    results: [SERVICE, VIEWS],
    total: 2,
    pendingQuery: null,
    loadingMore: false,
    failure: null,
    ...overrides,
  };
}

const AI_OFF: AiStatus = {
  enabled: false,
  provider: null,
  model: null,
  notice: null,
  searchNotice: null,
  dailyCallLimit: null,
  usage: null,
};

function fakeClient(aiEnabled = false) {
  return {
    getAiStatus: vi.fn().mockResolvedValue({...AI_OFF, enabled: aiEnabled}),
    getSearchOverview: vi.fn((analysisId: string, request: {q: string}) =>
      Promise.resolve({
        analysisId,
        query: request.q,
        intent: null,
        status: 'notGenerated',
        overview: null,
        metadata: null,
      } satisfies SearchOverviewResponse),
    ),
    generateSearchOverview: vi.fn(),
  };
}

function renderList(
  search: SearchState,
  selectedPath: string | null = null,
  client = fakeClient(),
) {
  const handlers = {
    onSelectFile: vi.fn(),
    onLoadMore: vi.fn(),
    onRefine: vi.fn(),
    onRetry: vi.fn(),
  };
  render(
    <ApiClientContext value={client as unknown as ApiClient}>
      <ReadingList
        analysisId="analysis-1"
        search={search}
        selectedPath={selectedPath}
        {...handlers}
      />
    </ApiClientContext>,
  );
  return handlers;
}

describe('ReadingList', () => {
  it('lists files in reading order without reasons', () => {
    renderList(searchState());

    const entries = screen
      .getAllByRole('listitem')
      .filter(li => li.classList.contains('reading-list__entry'));
    expect(entries).toHaveLength(2);
    const first = within(entries[0] as HTMLElement);
    expect(first.getByRole('button')).toHaveAccessibleName(
      '1. app/auth/service.py',
    );
    expect(first.queryByText(/Why/)).toBeNull();
    expect(first.queryByRole('link')).toBeNull();
  });

  it('selects a file', async () => {
    const user = userEvent.setup();
    const {onSelectFile} = renderList(searchState(), 'app/auth/views.py');

    expect(screen.getByRole('button', {name: /views\.py/})).toHaveAttribute(
      'aria-current',
      'true',
    );
    await user.click(screen.getByRole('button', {name: /service\.py/}));

    expect(onSelectFile).toHaveBeenCalledWith('app/auth/service.py');
  });

  it('lets the reader refine and reset the reading goal', async () => {
    const user = userEvent.setup();
    const {onRefine} = renderList(searchState());

    await user.selectOptions(
      screen.getByLabelText('What would you like to understand?'),
      'tests',
    );
    expect(onRefine).toHaveBeenCalledWith('tests');
    await user.selectOptions(
      screen.getByLabelText('What would you like to understand?'),
      '',
    );
    expect(onRefine).toHaveBeenLastCalledWith(undefined);
  });

  it('offers Show more when more results exist', async () => {
    const user = userEvent.setup();
    const {onLoadMore} = renderList(searchState({total: 34}));

    expect(screen.getByText(/Showing 2 of 34/)).toBeVisible();
    await user.click(screen.getByRole('button', {name: 'Show more (32 left)'}));

    expect(onLoadMore).toHaveBeenCalled();
  });

  it('says when results match keywords only, and why', () => {
    renderList(searchState({semanticStatus: 'over_budget'}));

    expect(
      screen.getByText(/larger than the server indexes for search by meaning/),
    ).toBeVisible();
  });

  it('says nothing extra when search by meaning was used', () => {
    renderList(searchState({semanticStatus: 'complete'}));

    expect(screen.queryByText(/keywords only/)).toBeNull();
  });

  it('announces how many files matched', () => {
    renderList(searchState({total: 34}));

    expect(screen.getByRole('status')).toHaveTextContent(
      '34 files match “login”.',
    );
  });

  it('suggests what to try when nothing matches', () => {
    renderList(searchState({query: 'kubernetes', results: [], total: 0}));

    expect(screen.getByText(/No files match/)).toHaveTextContent(
      'No files match “kubernetes”.',
    );
    expect(
      screen.getByText('Generated and vendored files are not searched.'),
    ).toBeVisible();
  });

  it('keeps the previous results while a new search runs', () => {
    renderList(searchState({pendingQuery: 'token'}));

    expect(screen.getByRole('status')).toHaveTextContent(
      'Searching for “token”…',
    );
    expect(screen.getByRole('button', {name: /service\.py/})).toBeVisible();
  });

  it('shows a failed search with Retry above the previous results', async () => {
    const user = userEvent.setup();
    const {onRetry} = renderList(
      searchState({
        failure: {
          request: 'search',
          query: 'token',
          code: 'TIMEOUT',
          error: {
            title: 'RepoLens is taking too long',
            message: 'Slow.',
            hint: null,
            retryable: true,
          },
        },
      }),
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'RepoLens is taking too long',
    );
    expect(screen.getByRole('button', {name: /service\.py/})).toBeVisible();
    await user.click(screen.getByRole('button', {name: 'Retry'}));
    expect(onRetry).toHaveBeenCalled();
  });

  it('offers the AI overview above the reading tour', async () => {
    const client = fakeClient(true);
    renderList(searchState({intent: 'tests'}), null, client);

    const overview = await screen.findByRole('region', {
      name: 'AI search overview',
    });
    const start = screen.getByRole('button', {name: /Start reading tour/});
    expect(
      overview.compareDocumentPosition(start) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      await within(overview).findByRole('button', {
        name: 'Generate AI overview',
      }),
    ).toBeVisible();
    expect(client.getSearchOverview).toHaveBeenCalledWith(
      'analysis-1',
      {q: 'login', intent: 'tests'},
      expect.anything(),
    );
    expect(client.generateSearchOverview).not.toHaveBeenCalled();
  });

  it('does not offer the AI overview when nothing matches', async () => {
    const client = fakeClient(true);
    renderList(searchState({results: [], total: 0}), null, client);

    expect(await screen.findByText(/No files match/)).toBeVisible();
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(
      screen.queryByRole('region', {name: 'AI search overview'}),
    ).not.toBeInTheDocument();
    expect(client.getAiStatus).not.toHaveBeenCalled();
    expect(client.getSearchOverview).not.toHaveBeenCalled();
  });
});

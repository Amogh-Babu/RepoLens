import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {RankedFile} from '../api/types.ts';
import type {SearchState} from '../state/analysisStore.ts';
import {ReadingList} from './ReadingList.tsx';

const SERVICE: RankedFile = {
  position: 1,
  path: 'app/auth/service.py',
  score: 40,
  reason: 'Defines login_user; imported by 2 other matching files',
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

function renderList(search: SearchState, selectedPath: string | null = null) {
  const handlers = {
    onSelectFile: vi.fn(),
    onLoadMore: vi.fn(),
    onRetry: vi.fn(),
  };
  render(
    <ReadingList
      search={search}
      selectedPath={selectedPath}
      sourceUrlFor={path => `https://github.com/o/r/blob/abc/${path}`}
      {...handlers}
    />,
  );
  return handlers;
}

describe('ReadingList', () => {
  it('lists files in reading order with reasons and source links', () => {
    renderList(searchState());

    const entries = screen
      .getAllByRole('listitem')
      .filter(li => li.classList.contains('reading-list__entry'));
    expect(entries).toHaveLength(2);
    const first = within(entries[0] as HTMLElement);
    expect(first.getByRole('button')).toHaveAccessibleName(
      '1. app/auth/service.py',
    );
    expect(first.getByText(/^Defines login_user/)).toBeVisible();
    expect(first.getByRole('link', {name: /Source/})).toHaveAttribute(
      'href',
      'https://github.com/o/r/blob/abc/app/auth/service.py',
    );
    expect(screen.getByText(/not the order the code runs in/)).toBeVisible();
  });

  it('expands an entry to show every match, linked to its line', async () => {
    const user = userEvent.setup();
    renderList(searchState());

    await user.click(screen.getAllByText('2 matches')[0] as HTMLElement);

    expect(screen.getByRole('link', {name: 'login_user'})).toHaveAttribute(
      'href',
      'https://github.com/o/r/blob/abc/app/auth/service.py#L22',
    );
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

  it('offers Show more when more results exist', async () => {
    const user = userEvent.setup();
    const {onLoadMore} = renderList(searchState({total: 34}));

    expect(screen.getByText(/Showing 2 of 34/)).toBeVisible();
    await user.click(screen.getByRole('button', {name: 'Show more (32 left)'}));

    expect(onLoadMore).toHaveBeenCalled();
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
});

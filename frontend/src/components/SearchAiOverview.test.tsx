import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {ReactNode} from 'react';
import {ApiClientContext} from '../api/apiClientContext.ts';
import type {ApiClient, GenerateSearchOverviewOptions} from '../api/client.ts';
import {ApiError} from '../api/errors.ts';
import type {
  AiStatus,
  SearchIntent,
  SearchOverviewRequest,
  SearchOverviewResponse,
} from '../api/types.ts';
import {SearchAiOverview} from './SearchAiOverview.tsx';

const ENABLED: AiStatus = {
  enabled: true,
  provider: 'OpenAI',
  model: 'gpt-5.4-mini',
  notice: "Generating sends this file's source to OpenAI.",
  searchNotice: 'Generating sends the matching files to OpenAI.',
  dailyCallLimit: 100,
  usage: null,
};
const DISABLED: AiStatus = {
  ...ENABLED,
  enabled: false,
  provider: null,
  model: null,
  notice: null,
  searchNotice: null,
};

function notGenerated(
  query = 'login',
  intent: SearchIntent | null = null,
): SearchOverviewResponse {
  return {
    analysisId: 'analysis-1',
    query,
    intent,
    status: 'notGenerated',
    overview: null,
    metadata: null,
  };
}

function completed(
  summary = 'Login starts in `service.py` and is exposed by the views.',
  cached = true,
): SearchOverviewResponse {
  return {
    ...notGenerated(),
    status: 'completed',
    overview: {
      summary,
      startHere: {
        path: 'app/auth/service.py',
        reason: 'Defines `login_user`, which the views call.',
      },
      readNext: [
        {path: 'app/auth/views.py', reason: 'Exposes login as a route.'},
        {path: 'tests/test_auth.py', reason: 'Shows the expected behavior.'},
      ],
      uncertainties: ['How sessions expire is not shown.'],
    },
    metadata: {
      model: 'gpt-5.4-mini',
      promptVersion: 'p1',
      schemaVersion: '1',
      generatedAt: '2026-11-24T10:00:00Z',
      cached,
      cacheStatus: cached ? 'hit' : 'miss',
      usedFileSummaries: [],
    },
  };
}

function fakeClient(
  options: {
    status?: AiStatus;
    cached?: SearchOverviewResponse | Error;
    generate?: (regenerate: boolean) => Promise<SearchOverviewResponse>;
  } = {},
) {
  return {
    getAiStatus: vi.fn().mockResolvedValue(options.status ?? ENABLED),
    getSearchOverview: vi.fn((_id: string, request: SearchOverviewRequest) =>
      options.cached instanceof Error
        ? Promise.reject(options.cached)
        : Promise.resolve(
            options.cached ?? notGenerated(request.q, request.intent ?? null),
          ),
    ),
    generateSearchOverview: vi.fn(
      (
        _id: string,
        _request: SearchOverviewRequest,
        request: GenerateSearchOverviewOptions = {},
      ) =>
        (
          options.generate ??
          (() => Promise.resolve(completed(undefined, false)))
        )(request.regenerate ?? false),
    ),
  };
}

function renderOverview(
  client: ReturnType<typeof fakeClient>,
  props: {query?: string; intent?: SearchIntent} = {},
) {
  const onSelectFile = vi.fn();
  const wrap = (node: ReactNode) => (
    <ApiClientContext value={client as unknown as ApiClient}>
      {node}
    </ApiClientContext>
  );
  const element = (next: {query?: string; intent?: SearchIntent}) => (
    <SearchAiOverview
      analysisId="analysis-1"
      query={next.query ?? 'login'}
      intent={next.intent}
      onSelectFile={onSelectFile}
    />
  );
  const result = render(wrap(element(props)));
  return {
    onSelectFile,
    rerender: (next: {query?: string; intent?: SearchIntent}) =>
      result.rerender(wrap(element(next))),
  };
}

function region() {
  return screen.findByRole('region', {name: 'AI search overview'});
}

describe('SearchAiOverview', () => {
  it('renders nothing when AI is disabled and never reads or generates', async () => {
    const client = fakeClient({status: DISABLED});
    renderOverview(client);

    await vi.waitFor(() => expect(client.getAiStatus).toHaveBeenCalled());
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(
      screen.queryByRole('region', {name: 'AI search overview'}),
    ).not.toBeInTheDocument();
    expect(client.getSearchOverview).not.toHaveBeenCalled();
    expect(client.generateSearchOverview).not.toHaveBeenCalled();
  });

  it('shows a cached overview at once without a model call', async () => {
    const client = fakeClient({cached: completed()});
    renderOverview(client, {intent: 'implementation'});

    const overview = await region();
    expect(await within(overview).findByText(/Login starts in/)).toBeVisible();
    expect(within(overview).getByText('Start here')).toBeVisible();
    expect(within(overview).getByText('Then read')).toBeVisible();
    expect(
      within(overview).getByText('How sessions expire is not shown.'),
    ).toBeVisible();
    expect(
      within(overview).getByText('AI-generated — check the files.'),
    ).toBeVisible();
    expect(within(overview).getByText('Cached')).toBeVisible();
    expect(client.getSearchOverview).toHaveBeenCalledWith(
      'analysis-1',
      {q: 'login', intent: 'implementation'},
      expect.objectContaining({signal: expect.any(AbortSignal)}),
    );
    expect(client.generateSearchOverview).not.toHaveBeenCalled();
  });

  it('generates only after the button is clicked', async () => {
    const user = userEvent.setup();
    const client = fakeClient();
    renderOverview(client);

    const overview = await region();
    const button = await within(overview).findByRole('button', {
      name: 'Generate AI overview',
    });
    expect(
      within(overview).getByText(
        'Generating sends the matching files to OpenAI.',
      ),
    ).toBeVisible();
    expect(client.generateSearchOverview).not.toHaveBeenCalled();

    await user.click(button);

    expect(await within(overview).findByText(/Login starts in/)).toBeVisible();
    expect(client.generateSearchOverview).toHaveBeenCalledTimes(1);
    expect(client.generateSearchOverview).toHaveBeenCalledWith(
      'analysis-1',
      {q: 'login', intent: null},
      {regenerate: false},
    );
    expect(
      within(overview).queryByRole('button', {name: 'Generate AI overview'}),
    ).not.toBeInTheDocument();
  });

  it('opens the files it names', async () => {
    const user = userEvent.setup();
    const client = fakeClient({cached: completed()});
    const {onSelectFile} = renderOverview(client);

    const overview = await region();
    await user.click(
      await within(overview).findByRole('button', {
        name: 'app/auth/service.py',
      }),
    );
    await user.click(
      within(overview).getByRole('button', {name: 'tests/test_auth.py'}),
    );

    expect(onSelectFile.mock.calls).toEqual([
      ['app/auth/service.py'],
      ['tests/test_auth.py'],
    ]);
  });

  it('starts over when the query or intent changes', async () => {
    const client = fakeClient();
    client.getSearchOverview.mockResolvedValueOnce(completed());
    const {rerender} = renderOverview(client);

    let overview = await region();
    await within(overview).findByText(/Login starts in/);

    rerender({query: 'logout'});
    overview = await region();
    expect(
      await within(overview).findByRole('button', {
        name: 'Generate AI overview',
      }),
    ).toBeVisible();
    expect(within(overview).queryByText(/Login starts in/)).toBeNull();

    rerender({query: 'logout', intent: 'tests'});
    await vi.waitFor(() =>
      expect(client.getSearchOverview).toHaveBeenCalledTimes(3),
    );
    expect(client.getSearchOverview.mock.calls.map(call => call[1])).toEqual([
      {q: 'login', intent: null},
      {q: 'logout', intent: null},
      {q: 'logout', intent: 'tests'},
    ]);
    expect(client.generateSearchOverview).not.toHaveBeenCalled();
  });

  it('keeps the previous overview when regenerating fails', async () => {
    const user = userEvent.setup();
    const client = fakeClient({
      cached: completed('Cached overview.'),
      generate: () =>
        Promise.reject(
          new ApiError(
            'AI_REGENERATE_COOLDOWN',
            'This overview was generated moments ago.',
            'Try again in a minute.',
            429,
          ),
        ),
    });
    renderOverview(client);

    const overview = await region();
    await within(overview).findByText('Cached overview.');
    await user.click(
      within(overview).getByRole('button', {name: 'Regenerate'}),
    );

    expect(await within(overview).findByRole('alert')).toHaveTextContent(
      'Generated moments ago',
    );
    expect(within(overview).getByText('Cached overview.')).toBeVisible();
    expect(
      within(overview).getByRole('button', {name: 'app/auth/service.py'}),
    ).toBeVisible();
    expect(client.generateSearchOverview).toHaveBeenCalledWith(
      'analysis-1',
      {q: 'login', intent: null},
      {regenerate: true},
    );
  });

  it('shows a failed cache read and lets the reader retry by generating', async () => {
    const user = userEvent.setup();
    const client = fakeClient({
      cached: new ApiError('AI_UNAVAILABLE', 'The AI service is down.'),
    });
    renderOverview(client);

    const overview = await region();
    expect(await within(overview).findByRole('alert')).toHaveTextContent(
      'The AI service is down.',
    );
    await user.click(within(overview).getByRole('button', {name: 'Retry'}));

    expect(await within(overview).findByText(/Login starts in/)).toBeVisible();
    expect(client.generateSearchOverview).toHaveBeenCalledWith(
      'analysis-1',
      {q: 'login', intent: null},
      {regenerate: false},
    );
  });

  it('never interprets model HTML as markup', async () => {
    const client = fakeClient({
      cached: completed('<img src=x onerror="alert(1)"> Bold <b>claim</b>'),
    });
    renderOverview(client);

    const overview = await region();
    expect(
      await within(overview).findByText(/<img src=x onerror=/),
    ).toBeVisible();
    expect(overview.querySelector('img')).toBeNull();
    expect(overview.querySelector('b')).toBeNull();
  });
});

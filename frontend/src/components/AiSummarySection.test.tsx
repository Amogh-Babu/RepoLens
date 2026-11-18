import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {ApiClientContext} from '../api/apiClientContext.ts';
import type {ApiClient} from '../api/client.ts';
import {ApiError} from '../api/errors.ts';
import type {
  AiStatus,
  CodeSummary,
  FileDetail,
  FileSummary,
  SummaryMetadata,
} from '../api/types.ts';
import {FileDetailPanel} from './FileDetailPanel.tsx';

const SHA = '3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f';
const REPO = 'https://github.com/someone/flask-auth';
const PATH = 'app/auth/service.py';
const BLOB = `${REPO}/blob/${SHA}/${PATH}`;

const ENABLED: AiStatus = {
  enabled: true,
  provider: 'OpenAI',
  model: 'gpt-5.4-mini',
  notice:
    "Generating a summary sends this file's source code to the configured AI provider (OpenAI).",
  dailyCallLimit: 100,
  usage: null,
};

const DISABLED: AiStatus = {
  enabled: false,
  provider: null,
  model: null,
  notice: null,
  dailyCallLimit: null,
  usage: null,
};

const NOT_GENERATED: FileSummary = {
  analysisId: 'analysis-1',
  path: PATH,
  sha: SHA,
  status: 'notGenerated',
  summary: null,
  metadata: null,
};

function completed(
  summary: Partial<CodeSummary> = {},
  metadata: Partial<SummaryMetadata> = {},
): FileSummary {
  return {
    ...NOT_GENERATED,
    status: 'completed',
    summary: {
      summary: 'Checks passwords and issues `Session` tokens.',
      purpose: 'Authentication service for the app.',
      responsibilities: [
        'Verifies passwords with werkzeug.',
        'Creates sessions.',
      ],
      keySymbols: [
        {
          name: 'authenticate',
          kind: 'function',
          description: 'Checks a password.',
          line: 9,
          url: `${BLOB}#L9`,
        },
      ],
      dependencies: [
        {
          path: 'app/models/user.py',
          relationship: 'imports',
          description: 'Loads users.',
        },
      ],
      sideEffects: [
        {
          kind: 'database',
          description: 'Updates the last login time.',
          startLine: 20,
          endLine: 22,
          url: `${BLOB}#L20-L22`,
        },
      ],
      uncertainties: ['The docstring of `authenticate` is outdated.'],
      evidence: [
        {
          startLine: 9,
          endLine: 18,
          description: 'Password check.',
          url: `${BLOB}#L9-L18`,
        },
      ],
      coverage: 'complete',
      ...summary,
    },
    metadata: {
      model: 'gpt-5.4-mini',
      promptVersion: 'p1',
      schemaVersion: '1',
      sourceHash: 'abc',
      generatedAt: '2026-11-17T10:00:00Z',
      cached: false,
      cacheStatus: 'miss',
      coverage: 'complete',
      inspectedLines: [[1, 54]],
      lineCount: 54,
      sourceUrl: BLOB,
      ...metadata,
    },
  };
}

const DETAIL: FileDetail = {
  path: PATH,
  module: 'app/auth',
  parsed: true,
  lineCount: 54,
  symbols: [{name: 'authenticate', kind: 'function', line: 9}],
  imports: [],
  importedBy: ['app/auth/views.py'],
  sourceUrl: BLOB,
};

interface FakeOptions {
  status?: AiStatus;
  cached?: FileSummary | Error;
  generate?: (regenerate: boolean) => Promise<FileSummary>;
}

function fakeClient(options: FakeOptions = {}) {
  const client = {
    getAiStatus: vi.fn().mockResolvedValue(options.status ?? ENABLED),
    getFileSummary: vi.fn(() =>
      options.cached instanceof Error
        ? Promise.reject(options.cached)
        : Promise.resolve(options.cached ?? NOT_GENERATED),
    ),
    generateFileSummary: vi.fn(
      (_id: string, _path: string, request: {regenerate?: boolean} = {}) =>
        (options.generate ?? (() => Promise.resolve(completed())))(
          request.regenerate ?? false,
        ),
    ),
  };
  return client;
}

function renderPanel(client: ReturnType<typeof fakeClient>, withAi = true) {
  const onSelectFile = vi.fn();
  render(
    <ApiClientContext value={client as unknown as ApiClient}>
      <FileDetailPanel
        path={PATH}
        analysisId={withAi ? 'analysis-1' : undefined}
        repoUrl={REPO}
        sha={SHA}
        detail={DETAIL}
        failure={null}
        onSelectFile={onSelectFile}
        onRetry={vi.fn()}
        onClose={vi.fn()}
      />
    </ApiClientContext>,
  );
  return {onSelectFile};
}

function aiSection() {
  return screen.getByRole('region', {name: /AI File Summary/});
}

describe('AiSummarySection', () => {
  it('says AI is off when the server has it disabled', async () => {
    const client = fakeClient({status: DISABLED});
    renderPanel(client);

    expect(
      await screen.findByText(/AI summaries are not enabled on this server/),
    ).toBeInTheDocument();
    expect(client.getFileSummary).not.toHaveBeenCalled();
    expect(
      screen.queryByRole('button', {name: 'Generate AI summary'}),
    ).not.toBeInTheDocument();
  });

  it('shows the provider notice and generates a summary on request', async () => {
    const user = userEvent.setup();
    const client = fakeClient();
    renderPanel(client);

    const generate = await screen.findByRole('button', {
      name: 'Generate AI summary',
    });
    expect(screen.getByText(/sends this file's source code/)).toBeVisible();
    expect(client.generateFileSummary).not.toHaveBeenCalled();

    await user.click(generate);

    expect(
      await screen.findByText(/Checks passwords and issues/),
    ).toBeInTheDocument();
    expect(client.generateFileSummary).toHaveBeenCalledWith(
      'analysis-1',
      PATH,
      {regenerate: false},
    );
    const section = aiSection();
    expect(within(section).getByText('AI-generated')).toBeInTheDocument();
    expect(within(section).getByText('Session').tagName).toBe('CODE');
    expect(
      within(section).getByText(/Generated by gpt-5.4-mini/),
    ).toBeVisible();
  });

  it('shows a loading state while generating without blocking the panel', async () => {
    const user = userEvent.setup();
    const client = fakeClient({generate: () => new Promise(() => {})});
    const {onSelectFile} = renderPanel(client);

    await user.click(
      await screen.findByRole('button', {name: 'Generate AI summary'}),
    );

    expect(
      within(aiSection()).getByText(/Generating and verifying a summary/),
    ).toBeInTheDocument();
    expect(aiSection()).toHaveAttribute('aria-busy', 'true');
    // The deterministic sections are still there and usable.
    expect(screen.getByRole('link', {name: 'authenticate'})).toHaveAttribute(
      'href',
      `${BLOB}#L9`,
    );
    await user.click(screen.getByRole('button', {name: 'app/auth/views.py'}));
    expect(onSelectFile).toHaveBeenCalledWith('app/auth/views.py');
  });

  it('shows a cached summary straight away, labelled as cached', async () => {
    const cached = completed({}, {cached: true, cacheStatus: 'hit'});
    const client = fakeClient({cached});
    renderPanel(client);

    expect(
      await screen.findByText(/Generated by gpt-5.4-mini · cached/),
    ).toBeVisible();
    expect(client.generateFileSummary).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Regenerate'})).toBeVisible();
  });

  it('links every evidence range and symbol to the analyzed commit', async () => {
    const user = userEvent.setup();
    renderPanel(fakeClient({cached: completed()}));

    await user.click(
      await screen.findByText(/Purpose, responsibilities and evidence/),
    );

    const section = aiSection();
    expect(
      within(section).getByRole('link', {name: /Lines 9–18/}),
    ).toHaveAttribute('href', `${BLOB}#L9-L18`);
    expect(
      within(section).getByRole('link', {name: /Lines 20–22/}),
    ).toHaveAttribute('href', `${BLOB}#L20-L22`);
    expect(
      within(section).getByRole('link', {name: 'authenticate'}),
    ).toHaveAttribute('href', `${BLOB}#L9`);
    for (const link of within(section).getAllByRole('link')) {
      expect(link.getAttribute('href')).toContain(`/blob/${SHA}/`);
    }
    expect(within(section).getByText(/is outdated/)).toBeVisible();
  });

  it('opens a verified dependency in the panel', async () => {
    const user = userEvent.setup();
    const {onSelectFile} = renderPanel(fakeClient({cached: completed()}));

    await user.click(
      await screen.findByText(/Purpose, responsibilities and evidence/),
    );
    await user.click(
      within(aiSection()).getByRole('button', {name: 'app/models/user.py'}),
    );

    expect(onSelectFile).toHaveBeenCalledWith('app/models/user.py');
  });

  it('regenerates a cached summary on request', async () => {
    const user = userEvent.setup();
    const fresh = completed({summary: 'A newer summary.'});
    const client = fakeClient({
      cached: completed(),
      generate: () => Promise.resolve(fresh),
    });
    renderPanel(client);

    await user.click(await screen.findByRole('button', {name: 'Regenerate'}));

    expect(await screen.findByText('A newer summary.')).toBeVisible();
    expect(client.generateFileSummary).toHaveBeenCalledWith(
      'analysis-1',
      PATH,
      {regenerate: true},
    );
  });

  it('shows a failure with a retry, keeping the deterministic panel', async () => {
    const user = userEvent.setup();
    let calls = 0;
    const client = fakeClient({
      generate: () => {
        calls += 1;
        return calls === 1
          ? Promise.reject(
              new ApiError(
                'AI_TIMEOUT',
                'The AI provider took too long to summarize this file.',
                'Try again.',
                504,
              ),
            )
          : Promise.resolve(completed());
      },
    });
    renderPanel(client);

    await user.click(
      await screen.findByRole('button', {name: 'Generate AI summary'}),
    );

    const alert = await within(aiSection()).findByRole('alert');
    expect(alert).toHaveTextContent('The AI summary took too long');
    expect(screen.getByRole('heading', {name: /Symbols/})).toBeVisible();
    await user.click(within(alert).getByRole('button', {name: 'Retry'}));
    expect(
      await screen.findByText(/Checks passwords and issues/),
    ).toBeVisible();
  });

  it('keeps the previous summary when regeneration is rate-limited', async () => {
    const user = userEvent.setup();
    const client = fakeClient({
      cached: completed(),
      generate: () =>
        Promise.reject(
          new ApiError(
            'AI_REGENERATE_COOLDOWN',
            'This summary was generated moments ago.',
            'Wait 42 seconds before regenerating it.',
            429,
          ),
        ),
    });
    renderPanel(client);

    await user.click(await screen.findByRole('button', {name: 'Regenerate'}));

    expect(await screen.findByText(/Wait 42 seconds/)).toBeVisible();
    expect(screen.getByText(/Checks passwords and issues/)).toBeVisible();
  });

  it('warns when only part of the file was inspected', async () => {
    const partial = completed(
      {coverage: 'partial'},
      {
        coverage: 'partial',
        inspectedLines: [
          [1, 20],
          [31, 40],
        ],
      },
    );
    renderPanel(fakeClient({cached: partial}));

    expect(
      await screen.findByText(/only lines 1–20, 31–40 of 54 were inspected/),
    ).toBeVisible();
  });

  it('renders generated text as text, never as HTML', async () => {
    const hostile = completed({
      summary: '<img src=x onerror="alert(1)"> Formats titles.',
    });
    renderPanel(fakeClient({cached: hostile}));

    expect(
      await screen.findByText(/<img src=x onerror="alert\(1\)"> Formats/),
    ).toBeVisible();
    expect(document.querySelector('img')).toBeNull();
  });

  it('treats a server that turned AI off as disabled', async () => {
    renderPanel(
      fakeClient({
        cached: new ApiError('AI_DISABLED', 'AI file summaries are off.'),
      }),
    );

    expect(
      await screen.findByText(/AI summaries are not enabled on this server/),
    ).toBeVisible();
  });

  it('is absent when the panel is rendered without an analysis id', () => {
    const client = fakeClient();
    renderPanel(client, false);

    expect(
      screen.queryByRole('region', {name: /AI File Summary/}),
    ).not.toBeInTheDocument();
    expect(client.getAiStatus).not.toHaveBeenCalled();
  });
});

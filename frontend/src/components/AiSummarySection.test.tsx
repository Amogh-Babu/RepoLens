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
} from '../api/types.ts';
import {FileDetailPanel} from './FileDetailPanel.tsx';

const SHA = '3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f';
const REPO = 'https://github.com/someone/flask-auth';
const PATH = 'app/auth/service.py';
const ENABLED: AiStatus = {
  enabled: true,
  provider: 'OpenAI',
  model: 'gpt-5.4-mini',
  notice: "Generating sends this file's source to OpenAI.",
  dailyCallLimit: 100,
  usage: null,
};
const DISABLED: AiStatus = {
  ...ENABLED,
  enabled: false,
  provider: null,
  model: null,
  notice: null,
};
const NOT_GENERATED: FileSummary = {
  analysisId: 'analysis-1',
  path: PATH,
  sha: SHA,
  status: 'notGenerated',
  summary: null,
  metadata: null,
};
const DETAIL: FileDetail = {
  path: PATH,
  module: 'app/auth',
  parsed: true,
  lineCount: 54,
  symbols: [{name: 'authenticate', kind: 'function', line: 9}],
  imports: [],
  importedBy: ['app/auth/views.py'],
  sourceUrl: `${REPO}/blob/${SHA}/${PATH}`,
};

function completed(
  text = 'Checks passwords and issues `Session` tokens.',
): FileSummary {
  const summary: CodeSummary = {
    summary: text,
    purpose: 'Authentication.',
    responsibilities: [],
    keySymbols: [],
    dependencies: [],
    sideEffects: [],
    uncertainties: [],
    evidence: [],
    coverage: 'complete',
  };
  return {
    ...NOT_GENERATED,
    status: 'completed',
    summary,
    metadata: {
      model: 'gpt-5.4-mini',
      promptVersion: 'p1',
      schemaVersion: '1',
      sourceHash: 'abc',
      generatedAt: '2026-11-17T10:00:00Z',
      cached: true,
      cacheStatus: 'hit',
      coverage: 'complete',
      inspectedLines: [[1, 54]],
      lineCount: 54,
      sourceUrl: `${REPO}/blob/${SHA}/${PATH}`,
    },
  };
}

function fakeClient(
  options: {
    status?: AiStatus;
    cached?: FileSummary | Error;
    generate?: (regenerate: boolean) => Promise<FileSummary>;
  } = {},
) {
  return {
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
}

function renderPanel(client: ReturnType<typeof fakeClient>) {
  render(
    <ApiClientContext value={client as unknown as ApiClient}>
      <FileDetailPanel
        path={PATH}
        analysisId="analysis-1"
        repoUrl={REPO}
        sha={SHA}
        detail={DETAIL}
        failure={null}
        onSelectFile={vi.fn()}
        onRetry={vi.fn()}
        onClose={vi.fn()}
      />
    </ApiClientContext>,
  );
  return screen.getByRole('region', {name: 'AI overview'});
}

describe('AI File Overview integration', () => {
  it('falls back silently when AI is disabled and never reads or generates', async () => {
    const client = fakeClient({status: DISABLED});
    const overview = renderPanel(client);
    await vi.waitFor(() => expect(client.getAiStatus).toHaveBeenCalledOnce());
    expect(client.getFileSummary).not.toHaveBeenCalled();
    expect(client.generateFileSummary).not.toHaveBeenCalled();
    expect(overview).toBeEmptyDOMElement();
  });

  it('automatically displays a cached summary without a model call', async () => {
    const client = fakeClient({cached: completed()});
    const overview = renderPanel(client);
    expect(await within(overview).findByText(/Checks passwords/)).toBeVisible();
    expect(within(overview).getByText('Session').tagName).toBe('CODE');
    expect(client.getFileSummary).toHaveBeenCalledWith(
      'analysis-1',
      PATH,
      expect.any(Object),
    );
    expect(client.generateFileSummary).not.toHaveBeenCalled();
    expect(screen.queryByText('AI File Summary')).not.toBeInTheDocument();
  });

  it('shows structured details, evidence, and an AI accuracy disclaimer', async () => {
    const user = userEvent.setup();
    const item = completed();
    if (item.summary === null) throw new Error('Missing summary fixture');
    item.summary.purpose = 'Authenticate sessions';
    item.summary.responsibilities = ['Verify stored passwords'];
    item.summary.keySymbols = [
      {
        name: 'authenticate',
        kind: 'function',
        line: 9,
        description: 'Check credentials.',
        url: `${REPO}/blob/${SHA}/${PATH}#L9`,
      },
    ];
    item.summary.dependencies = [
      {
        path: 'app/auth/views.py',
        relationship: 'importedBy',
        description: 'Called by the request handler.',
      },
    ];
    item.summary.sideEffects = [
      {
        kind: 'filesystem',
        description: 'Write session data.',
        startLine: 15,
        endLine: 16,
        url: `${REPO}/blob/${SHA}/${PATH}#L15-L16`,
      },
    ];
    item.summary.uncertainties = ['Cannot confirm external login behavior.'];
    item.summary.evidence = [
      {
        startLine: 9,
        endLine: 14,
        description: 'Authentication implementation.',
        url: `${REPO}/blob/${SHA}/${PATH}#L9-L14`,
      },
    ];
    const overview = renderPanel(fakeClient({cached: item}));
    expect(
      await within(overview).findByText('AI-generated overview'),
    ).toBeVisible();
    expect(within(overview).getByText(/may still be inaccurate/)).toBeVisible();
    await user.click(
      within(overview).getByText('Purpose and responsibilities'),
    );
    expect(within(overview).getByText('Verify stored passwords')).toBeVisible();
    await user.click(within(overview).getByText('Key symbols (1)'));
    expect(
      within(overview).getByRole('link', {name: /authenticate/}),
    ).toHaveAttribute('href', `${REPO}/blob/${SHA}/${PATH}#L9`);
    await user.click(within(overview).getByText('Dependencies (1)'));
    expect(within(overview).getByText('app/auth/views.py')).toBeVisible();
    await user.click(within(overview).getByText('Side effects (1)'));
    expect(
      within(overview).getByRole('link', {name: /filesystem/}),
    ).toHaveAttribute('href', `${REPO}/blob/${SHA}/${PATH}#L15-L16`);
    await user.click(within(overview).getByText('Uncertainties (1)'));
    expect(
      within(overview).getByText('Cannot confirm external login behavior.'),
    ).toBeVisible();
    await user.click(within(overview).getByText('Source evidence (1)'));
    expect(
      within(overview).getByRole('link', {name: /Lines 9/}),
    ).toHaveAttribute('href', `${REPO}/blob/${SHA}/${PATH}#L9-L14`);
  });

  it('warns about partial source coverage and shows inspected ranges', async () => {
    const item = completed();
    if (item.summary === null || item.metadata === null) {
      throw new Error('Missing summary fixture');
    }
    item.summary.coverage = 'partial';
    item.metadata.coverage = 'partial';
    item.metadata.inspectedLines = [
      [1, 20],
      [30, 40],
    ];
    const overview = renderPanel(fakeClient({cached: item}));
    expect(await within(overview).findByRole('note')).toHaveTextContent(
      'Partial summary: only part of this file was inspected.',
    );
    expect(within(overview).getByText(/1–20, 30–40/)).toBeVisible();
  });

  it('never interprets model HTML as active markup', async () => {
    const overview = renderPanel(
      fakeClient({cached: completed('<img src=x onerror=alert(1)>')}),
    );
    expect(
      await within(overview).findByText('<img src=x onerror=alert(1)>'),
    ).toBeVisible();
    expect(within(overview).queryByRole('img')).not.toBeInTheDocument();
  });

  it('offers generation on a cache miss and calls POST only after a click', async () => {
    const user = userEvent.setup();
    const client = fakeClient();
    const overview = renderPanel(client);
    const button = await within(overview).findByRole('button', {
      name: 'Generate AI overview',
    });
    expect(client.generateFileSummary).not.toHaveBeenCalled();
    await user.click(button);
    expect(await within(overview).findByText(/Checks passwords/)).toBeVisible();
    expect(client.generateFileSummary).toHaveBeenCalledWith(
      'analysis-1',
      PATH,
      {regenerate: false},
    );
  });

  it('regenerates only after an explicit click', async () => {
    const user = userEvent.setup();
    const client = fakeClient({
      cached: completed('Cached text.'),
      generate: () => Promise.resolve(completed('Fresh text.')),
    });
    const overview = renderPanel(client);
    await within(overview).findByText('Cached text.');
    expect(client.generateFileSummary).not.toHaveBeenCalled();
    await user.click(
      within(overview).getByRole('button', {name: 'Regenerate'}),
    );
    expect(await within(overview).findByText('Fresh text.')).toBeVisible();
    expect(client.generateFileSummary).toHaveBeenCalledWith(
      'analysis-1',
      PATH,
      {regenerate: true},
    );
  });

  it('keeps a cached summary visible when regeneration fails', async () => {
    const user = userEvent.setup();
    const client = fakeClient({
      cached: completed('Cached text.'),
      generate: () =>
        Promise.reject(new ApiError('AI_PROVIDER_FAILED', 'Provider failed.')),
    });
    const overview = renderPanel(client);
    await within(overview).findByText('Cached text.');
    await user.click(
      within(overview).getByRole('button', {name: 'Regenerate'}),
    );
    expect(await within(overview).findByText('Cached text.')).toBeVisible();
    expect(within(overview).getByText(/Provider failed/)).toBeVisible();
  });

  it('explains the per-visitor limit without offering a retry', async () => {
    const user = userEvent.setup();
    const client = fakeClient({
      generate: () =>
        Promise.reject(
          new ApiError(
            'AI_CLIENT_LIMIT',
            'You have generated 10 new AI summaries in the last hour.',
            'Cached summaries are still available. You can generate more in about 12 minutes.',
            429,
          ),
        ),
    });
    const overview = renderPanel(client);
    await user.click(
      await within(overview).findByRole('button', {
        name: 'Generate AI overview',
      }),
    );
    expect(
      await within(overview).findByText('AI generation limit reached'),
    ).toBeVisible();
    expect(within(overview).getByText(/about 12 minutes/)).toBeVisible();
    expect(
      within(overview).queryByRole('button', {name: 'Retry'}),
    ).not.toBeInTheDocument();
  });

  it('leaves file details usable while generation is pending', async () => {
    const user = userEvent.setup();
    const client = fakeClient({generate: () => new Promise(() => {})});
    const overview = renderPanel(client);
    await user.click(
      await within(overview).findByRole('button', {
        name: 'Generate AI overview',
      }),
    );
    expect(
      within(overview).getByRole('status', {name: /Generating AI overview/}),
    ).toBeVisible();
    expect(screen.getByRole('heading', {name: 'service.py'})).toBeVisible();
    expect(screen.getByText('File info')).toBeVisible();
  });
});

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

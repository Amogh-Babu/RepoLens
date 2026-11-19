import {fireEvent, render, screen} from '@testing-library/react';
import {ApiClientContext} from '../api/apiClientContext.ts';
import type {ApiClient} from '../api/client.ts';
import type {RepositoryOverview} from '../api/types.ts';
import {OverviewPanel} from './OverviewPanel.tsx';

const OVERVIEW: RepositoryOverview = {
  entryPoints: [
    {
      path: 'app/main.py',
      reason: 'Start here.',
      summary: 'Creates the application.',
    },
  ],
  coreFiles: [],
  architecture: {
    packages: [{id: 'app', name: 'app', fileCount: 1, layer: 0, cyclic: false}],
    edges: [],
    layers: [{depth: 0, name: 'Foundations', packages: ['app']}],
    hasCycles: false,
  },
  areas: [
    {
      id: 'app/main.py',
      name: 'app',
      files: ['app/main.py'],
      summary: '1 file.',
    },
  ],
  tour: [
    {
      path: 'app/main.py',
      reason: 'Start here.',
      summary: 'Creates the application.',
    },
  ],
  categories: [{path: 'app/main.py', category: 'source'}],
};

describe('OverviewPanel', () => {
  it('shows repo guidance and opens the selected file', async () => {
    const onSelectFile = vi.fn();
    const onSelectArea = vi.fn();
    const client = {
      getOverview: vi.fn().mockResolvedValue(OVERVIEW),
    } as unknown as ApiClient;
    render(
      <ApiClientContext value={client}>
        <OverviewPanel
          analysisId="analysis-1"
          onSelectFile={onSelectFile}
          onSelectArea={onSelectArea}
        />
      </ApiClientContext>,
    );

    await screen.findByRole('heading', {name: 'Start here'});
    expect(screen.getAllByText('Creates the application.')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', {name: 'Start'}));
    fireEvent.click(screen.getByRole('button', {name: /app.*1 files/}));

    expect(onSelectFile).toHaveBeenCalledWith('app/main.py');
    expect(onSelectArea).toHaveBeenCalledWith(['app/main.py']);
  });

  it('labels verified AI descriptions and leaves static ones unlabelled', async () => {
    const client = {
      getOverview: vi.fn().mockResolvedValue({
        ...OVERVIEW,
        entryPoints: [
          {
            path: 'app/main.py',
            reason: 'Start here.',
            summary: 'Builds the Flask app and registers routes.',
            summarySource: 'ai',
          },
        ],
        tour: [
          {
            path: 'app/main.py',
            reason: 'Start here.',
            summary: 'Creates the application.',
            summarySource: 'static',
          },
        ],
      }),
    } as unknown as ApiClient;
    render(
      <ApiClientContext value={client}>
        <OverviewPanel
          analysisId="analysis-1"
          onSelectFile={vi.fn()}
          onSelectArea={vi.fn()}
        />
      </ApiClientContext>,
    );

    const aiText = await screen.findByText(
      'Builds the Flask app and registers routes.',
      {exact: false},
    );
    expect(aiText).toHaveTextContent(/^AI summary:/);
    expect(screen.getAllByText('AI')).toHaveLength(1);
  });
});

import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {FileDetail} from '../api/types.ts';
import {FileDetailPanel} from './FileDetailPanel.tsx';

const SHA = '3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f';
const REPO = 'https://github.com/someone/flask-auth';

const SERVICE: FileDetail = {
  path: 'app/auth/service.py',
  module: 'app/auth',
  parsed: true,
  lineCount: 54,
  symbols: [
    {name: 'authenticate', kind: 'function', line: 9},
    {name: 'Session', kind: 'class', line: 30},
  ],
  imports: [
    {
      rawName: 'app.models.user',
      kind: 'internal',
      targetPath: 'app/models/user.py',
      targetPackage: null,
    },
    {
      rawName: 'werkzeug.security',
      kind: 'external',
      targetPath: null,
      targetPackage: 'werkzeug',
    },
    {
      rawName: 'flask',
      kind: 'external',
      targetPath: null,
      targetPackage: 'flask',
    },
    {
      rawName: 'plugins.loader',
      kind: 'unresolved',
      targetPath: null,
      targetPackage: null,
    },
  ],
  importedBy: ['app/auth/views.py', 'tests/test_auth.py'],
  sourceUrl: `${REPO}/blob/${SHA}/app/auth/service.py`,
};

function renderPanel(
  props: Partial<Parameters<typeof FileDetailPanel>[0]> = {},
) {
  const handlers = {
    onSelectFile: vi.fn(),
    onRetry: vi.fn(),
    onClose: vi.fn(),
  };
  render(
    <FileDetailPanel
      path={SERVICE.path}
      repoUrl={REPO}
      sha={SHA}
      detail={SERVICE}
      failure={null}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

function section(title: string) {
  const heading = screen.getByRole('heading', {name: new RegExp(`^${title}`)});
  const element = heading.closest('section');
  if (element === null) throw new Error(`No section for ${title}`);
  return within(element);
}

describe('FileDetailPanel', () => {
  it('shows the path, commit and a source link pinned to the commit', () => {
    renderPanel();

    expect(
      screen.getByRole('heading', {name: 'service.py'}),
    ).toBeInTheDocument();
    expect(screen.getByText('app/auth/service.py')).toBeInTheDocument();
    expect(screen.getByText('3f9c2a1')).toBeInTheDocument();
    const link = screen.getByRole('link', {name: /Open source on GitHub/});
    expect(link).toHaveAttribute('href', SERVICE.sourceUrl);
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('links each symbol to its line', () => {
    renderPanel();

    expect(
      section('Symbols').getByRole('link', {name: 'authenticate'}),
    ).toHaveAttribute('href', `${SERVICE.sourceUrl}#L9`);
  });

  it('groups imports by kind', () => {
    renderPanel();

    expect(section('Imports').getByText('app/models/user.py')).toBeVisible();
    expect(
      section('External libraries')
        .getAllByRole('listitem')
        .map(li => li.textContent),
    ).toEqual(['flask', 'werkzeug']);
    expect(
      section('Unresolved imports').getByText('plugins.loader'),
    ).toBeVisible();
  });

  it('moves the selection to an imported or importing file', async () => {
    const user = userEvent.setup();
    const {onSelectFile} = renderPanel();

    await user.click(screen.getByRole('button', {name: 'app/models/user.py'}));
    await user.click(screen.getByRole('button', {name: 'tests/test_auth.py'}));

    expect(onSelectFile.mock.calls).toEqual([
      ['app/models/user.py'],
      ['tests/test_auth.py'],
    ]);
  });

  it('warns that an unparsed file has no dependency information', () => {
    renderPanel({
      path: 'app/broken.py',
      detail: {
        ...SERVICE,
        path: 'app/broken.py',
        parsed: false,
        symbols: [],
        imports: [],
        importedBy: [],
        sourceUrl: `${REPO}/blob/${SHA}/app/broken.py`,
      },
    });

    expect(screen.getByRole('note')).toHaveTextContent('could not be parsed');
    expect(screen.queryByRole('heading', {name: /^Symbols/})).toBeNull();
    expect(
      screen.getByRole('link', {name: /Open source on GitHub/}),
    ).toBeInTheDocument();
  });

  it('says plainly when a file has no imports and no importers', () => {
    renderPanel({detail: {...SERVICE, imports: [], importedBy: []}});

    expect(
      screen.getByText(/imports nothing and no other analyzed file/),
    ).toBeInTheDocument();
  });

  it('links the source and shows the path while details load', () => {
    renderPanel({detail: null});

    expect(screen.getByRole('status')).toHaveTextContent('Loading');
    expect(
      screen.getByRole('link', {name: /Open source on GitHub/}),
    ).toHaveAttribute('href', `${REPO}/blob/${SHA}/app/auth/service.py`);
  });

  it('shows a failure with Retry', async () => {
    const user = userEvent.setup();
    const {onRetry} = renderPanel({
      detail: null,
      failure: {
        code: 'TIMEOUT',
        error: {
          title: 'RepoLens is taking too long',
          message: 'Slow.',
          hint: null,
          retryable: true,
        },
      },
    });

    await user.click(screen.getByRole('button', {name: 'Retry'}));

    expect(onRetry).toHaveBeenCalled();
  });

  it('closes', async () => {
    const user = userEvent.setup();
    const {onClose} = renderPanel();

    await user.click(screen.getByRole('button', {name: 'Close file details'}));

    expect(onClose).toHaveBeenCalled();
  });
});

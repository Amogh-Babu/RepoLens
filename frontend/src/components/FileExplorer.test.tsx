import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {useState} from 'react';
import type {FileNode} from '../api/types.ts';
import {FileExplorer} from './FileExplorer.tsx';

const FILES: FileNode[] = [
  {path: 'manage.py', module: '.', parsed: true, lineCount: 10},
  {path: 'app/views.py', module: 'app', parsed: true, lineCount: 10},
  {path: 'app/auth/login.py', module: 'app/auth', parsed: true, lineCount: 10},
  {path: 'app/broken.py', module: 'app', parsed: false, lineCount: 3},
];

function renderExplorer(initiallyExpanded: string[] = []) {
  const onSelectFile = vi.fn();
  function Harness() {
    const [expanded, setExpanded] = useState(new Set(initiallyExpanded));
    const [selected, setSelected] = useState<string | null>(null);
    return (
      <FileExplorer
        files={FILES}
        selectedPath={selected}
        expandedDirs={expanded}
        onSelectFile={path => {
          setSelected(path);
          onSelectFile(path);
        }}
        onToggleDir={(path, value) =>
          setExpanded(current => {
            const next = new Set(current);
            if (value ?? !next.has(path)) {
              next.add(path);
            } else {
              next.delete(path);
            }
            return next;
          })
        }
      />
    );
  }
  render(<Harness />);
  return {onSelectFile};
}

function item(name: RegExp | string) {
  return screen.getByRole('treeitem', {name});
}

describe('FileExplorer', () => {
  it('shows top-level rows, expanding a directory on click', async () => {
    const user = userEvent.setup();
    renderExplorer();

    expect(screen.getAllByRole('treeitem')).toHaveLength(2);
    expect(item('app/')).toHaveAttribute('aria-expanded', 'false');

    await user.click(item('app/'));

    expect(item('app/')).toHaveAttribute('aria-expanded', 'true');
    expect(item('views.py')).toHaveAttribute('aria-level', '2');
  });

  it('selects a file on click', async () => {
    const user = userEvent.setup();
    const {onSelectFile} = renderExplorer(['app']);

    await user.click(item('views.py'));

    expect(onSelectFile).toHaveBeenCalledWith('app/views.py');
    expect(item('views.py')).toHaveAttribute('aria-selected', 'true');
  });

  it('marks files that could not be parsed', () => {
    renderExplorer(['app']);

    expect(item(/broken\.py/)).toHaveTextContent('not parsed');
  });

  it('has a single tab stop', () => {
    renderExplorer(['app']);

    const tabbable = screen
      .getAllByRole('treeitem')
      .filter(el => el.getAttribute('tabindex') === '0');
    expect(tabbable).toHaveLength(1);
  });

  it('supports the tree keyboard pattern', async () => {
    const user = userEvent.setup();
    const {onSelectFile} = renderExplorer();

    await user.tab();
    expect(item('app/')).toHaveFocus();

    // Right expands, Right again moves into the directory.
    await user.keyboard('{ArrowRight}');
    expect(item('app/')).toHaveAttribute('aria-expanded', 'true');
    await user.keyboard('{ArrowRight}');
    expect(item('auth/')).toHaveFocus();

    // Down moves through visible rows; Enter selects a file.
    await user.keyboard('{ArrowDown}');
    expect(item(/broken\.py/)).toHaveFocus();
    await user.keyboard('{ArrowDown}{Enter}');
    expect(onSelectFile).toHaveBeenCalledWith('app/views.py');

    // Left moves to the parent, then collapses it.
    await user.keyboard('{ArrowLeft}');
    expect(item('app/')).toHaveFocus();
    await user.keyboard('{ArrowLeft}');
    expect(item('app/')).toHaveAttribute('aria-expanded', 'false');

    await user.keyboard('{End}');
    expect(item('manage.py')).toHaveFocus();
    await user.keyboard('{Home}');
    expect(item('app/')).toHaveFocus();
  });
});

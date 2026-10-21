import type {FileNode} from '../api/types.ts';
import {
  ancestorDirs,
  buildFileTree,
  topLevelDirs,
  visibleRows,
} from './fileTree.ts';

function file(path: string): FileNode {
  return {path, module: '.', parsed: true, lineCount: 1};
}

const FILES = [
  'setup.py',
  'pkg/b.py',
  'pkg/sub/c.py',
  'pkg/a.py',
  'README_helper.py',
  'tests/test_a.py',
].map(file);

describe('buildFileTree', () => {
  it('nests files under directories, directories first, sorted by name', () => {
    const tree = buildFileTree(FILES);

    expect(tree.map(n => `${n.type}:${n.name}`)).toEqual([
      'dir:pkg',
      'dir:tests',
      'file:README_helper.py',
      'file:setup.py',
    ]);
    const pkg = tree[0];
    expect(pkg?.type === 'dir' && pkg.children.map(n => n.path)).toEqual([
      'pkg/sub',
      'pkg/a.py',
      'pkg/b.py',
    ]);
  });
});

describe('visibleRows', () => {
  const tree = buildFileTree(FILES);

  it('shows only top-level rows when nothing is expanded', () => {
    expect(visibleRows(tree, new Set()).map(r => r.node.path)).toEqual([
      'pkg',
      'tests',
      'README_helper.py',
      'setup.py',
    ]);
  });

  it('shows the children of expanded directories with their level', () => {
    const rows = visibleRows(tree, new Set(['pkg', 'pkg/sub']));

    expect(rows.map(r => [r.node.path, r.level])).toEqual([
      ['pkg', 1],
      ['pkg/sub', 2],
      ['pkg/sub/c.py', 3],
      ['pkg/a.py', 2],
      ['pkg/b.py', 2],
      ['tests', 1],
      ['README_helper.py', 1],
      ['setup.py', 1],
    ]);
    expect(rows[3]).toMatchObject({
      parentPath: 'pkg',
      setSize: 3,
      posInSet: 2,
    });
  });
});

describe('path helpers', () => {
  it('lists ancestor directories outermost first', () => {
    expect(ancestorDirs('a/b/c.py')).toEqual(['a', 'a/b']);
    expect(ancestorDirs('top.py')).toEqual([]);
  });

  it('lists distinct top-level directories', () => {
    expect(topLevelDirs(['a/x.py', 'a/b/y.py', 'c/z.py', 'root.py'])).toEqual([
      'a',
      'c',
    ]);
  });
});

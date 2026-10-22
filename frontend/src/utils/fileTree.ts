import type {FileNode} from '../api/types.ts';

export interface DirTreeNode {
  type: 'dir';
  /** Directory path, e.g. "app/auth". */
  path: string;
  name: string;
  children: TreeNode[];
}

export interface FileTreeNode {
  type: 'file';
  path: string;
  name: string;
  file: FileNode;
}

export type TreeNode = DirTreeNode | FileTreeNode;

/**
 * Builds a directory tree from file paths. Each level lists directories
 * first, then files, each sorted by name.
 */
export function buildFileTree(files: readonly FileNode[]): TreeNode[] {
  const root: DirTreeNode = {type: 'dir', path: '', name: '', children: []};
  const dirs = new Map<string, DirTreeNode>([['', root]]);

  function dirFor(path: string): DirTreeNode {
    const existing = dirs.get(path);
    if (existing !== undefined) return existing;
    const slash = path.lastIndexOf('/');
    const parent = dirFor(slash === -1 ? '' : path.slice(0, slash));
    const dir: DirTreeNode = {
      type: 'dir',
      path,
      name: path.slice(slash + 1),
      children: [],
    };
    parent.children.push(dir);
    dirs.set(path, dir);
    return dir;
  }

  for (const file of files) {
    const slash = file.path.lastIndexOf('/');
    const parent = dirFor(slash === -1 ? '' : file.path.slice(0, slash));
    parent.children.push({
      type: 'file',
      path: file.path,
      name: file.path.slice(slash + 1),
      file,
    });
  }

  for (const dir of dirs.values()) {
    dir.children.sort(
      (a, b) =>
        Number(a.type === 'file') - Number(b.type === 'file') ||
        a.name.localeCompare(b.name),
    );
  }
  return root.children;
}

/** A tree node as one row of the explorer, with its ARIA position. */
export interface VisibleRow {
  node: TreeNode;
  /** 1-based nesting level. */
  level: number;
  /** Path of the parent directory, or null at the top level. */
  parentPath: string | null;
  setSize: number;
  posInSet: number;
}

/** The rows the explorer shows, given which directories are expanded. */
export function visibleRows(
  nodes: readonly TreeNode[],
  expanded: ReadonlySet<string>,
  level = 1,
  parentPath: string | null = null,
): VisibleRow[] {
  return nodes.flatMap((node, index) => {
    const row: VisibleRow = {
      node,
      level,
      parentPath,
      setSize: nodes.length,
      posInSet: index + 1,
    };
    return node.type === 'dir' && expanded.has(node.path)
      ? [row, ...visibleRows(node.children, expanded, level + 1, node.path)]
      : [row];
  });
}

/** The directories containing a file, outermost first: "a", "a/b". */
export function ancestorDirs(path: string): string[] {
  const parts = path.split('/').slice(0, -1);
  return parts.map((_part, i) => parts.slice(0, i + 1).join('/'));
}

/** The distinct top-level directories among some file paths. */
export function topLevelDirs(paths: readonly string[]): string[] {
  return [
    ...new Set(
      paths.filter(p => p.includes('/')).map(p => p.slice(0, p.indexOf('/'))),
    ),
  ];
}

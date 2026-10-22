import type {KeyboardEvent} from 'react';
import {useEffect, useMemo, useRef, useState} from 'react';
import type {FileNode} from '../api/types.ts';
import type {VisibleRow} from '../utils/fileTree.ts';
import {buildFileTree, visibleRows} from '../utils/fileTree.ts';
import './FileExplorer.css';

interface FileExplorerProps {
  files: readonly FileNode[];
  selectedPath: string | null;
  expandedDirs: ReadonlySet<string>;
  onSelectFile: (path: string) => void;
  onToggleDir: (path: string, expanded?: boolean) => void;
}

function rowKey(row: VisibleRow): string {
  return `${row.node.type}:${row.node.path}`;
}

/**
 * Tree of the analyzed files. Follows the WAI-ARIA tree pattern: one tab
 * stop, arrow keys to move, Right/Left to expand and collapse, Enter or
 * Space to select a file.
 */
export function FileExplorer({
  files,
  selectedPath,
  expandedDirs,
  onSelectFile,
  onToggleDir,
}: FileExplorerProps) {
  const tree = useMemo(() => buildFileTree(files), [files]);
  const rows = useMemo(
    () => visibleRows(tree, expandedDirs),
    [tree, expandedDirs],
  );
  const items = useRef(new Map<string, HTMLLIElement>());
  const [focusedKey, setFocusedKey] = useState<string | null>(null);

  // The tab stop: the focused row if still visible, else the selected file,
  // else the first row.
  const tabStopKey =
    rows.find(row => rowKey(row) === focusedKey) !== undefined
      ? focusedKey
      : selectedPath !== null &&
          rows.some(row => rowKey(row) === `file:${selectedPath}`)
        ? `file:${selectedPath}`
        : rows[0] !== undefined
          ? rowKey(rows[0])
          : null;

  // Keep the selected file in view when it is selected from elsewhere.
  useEffect(() => {
    if (selectedPath === null) return;
    items.current.get(`file:${selectedPath}`)?.scrollIntoView?.({
      block: 'nearest',
    });
  }, [selectedPath, rows]);

  function focusRow(row: VisibleRow | undefined) {
    if (row === undefined) return;
    const key = rowKey(row);
    setFocusedKey(key);
    items.current.get(key)?.focus();
  }

  function activate(row: VisibleRow) {
    if (row.node.type === 'file') {
      onSelectFile(row.node.path);
    } else {
      onToggleDir(row.node.path);
    }
  }

  function handleKeyDown(event: KeyboardEvent, index: number) {
    const row = rows[index];
    if (row === undefined) return;
    const isDir = row.node.type === 'dir';
    const isExpanded = isDir && expandedDirs.has(row.node.path);

    switch (event.key) {
      case 'ArrowDown':
        focusRow(rows[index + 1]);
        break;
      case 'ArrowUp':
        focusRow(rows[index - 1]);
        break;
      case 'Home':
        focusRow(rows[0]);
        break;
      case 'End':
        focusRow(rows[rows.length - 1]);
        break;
      case 'ArrowRight':
        if (isDir && !isExpanded) {
          onToggleDir(row.node.path, true);
        } else if (isExpanded) {
          focusRow(rows[index + 1]);
        }
        break;
      case 'ArrowLeft':
        if (isExpanded) {
          onToggleDir(row.node.path, false);
        } else if (row.parentPath !== null) {
          focusRow(
            rows.find(
              r => r.node.type === 'dir' && r.node.path === row.parentPath,
            ),
          );
        }
        break;
      case 'Enter':
      case ' ':
        activate(row);
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  if (rows.length === 0) {
    return <p className="explorer__empty">No files were analyzed.</p>;
  }

  return (
    <ul className="explorer" role="tree" aria-label="Files">
      {rows.map((row, index) => {
        const key = rowKey(row);
        const {node} = row;
        const isDir = node.type === 'dir';
        const unparsed = node.type === 'file' && !node.file.parsed;
        return (
          <li
            key={key}
            ref={element => {
              if (element === null) {
                items.current.delete(key);
              } else {
                items.current.set(key, element);
              }
            }}
            role="treeitem"
            className={`explorer__row explorer__row--${node.type}`}
            style={{paddingLeft: `${(row.level - 1) * 16 + 8}px`}}
            aria-level={row.level}
            aria-setsize={row.setSize}
            aria-posinset={row.posInSet}
            aria-expanded={isDir ? expandedDirs.has(node.path) : undefined}
            aria-selected={isDir ? undefined : node.path === selectedPath}
            tabIndex={key === tabStopKey ? 0 : -1}
            title={node.path}
            onClick={() => {
              setFocusedKey(key);
              activate(row);
            }}
            onFocus={() => setFocusedKey(key)}
            onKeyDown={event => handleKeyDown(event, index)}
          >
            <span className="explorer__icon" aria-hidden="true">
              {isDir ? (expandedDirs.has(node.path) ? '▾' : '▸') : ''}
            </span>
            <span className="explorer__name">
              {node.name}
              {isDir && '/'}
            </span>
            {unparsed && (
              <span className="explorer__badge" title="Could not be parsed">
                not parsed
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

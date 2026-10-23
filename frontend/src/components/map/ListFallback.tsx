import type {ReactNode} from 'react';
import {useMemo} from 'react';
import type {DependencyGraph} from '../../api/types.ts';
import './ListFallback.css';

interface ListFallbackProps {
  graph: DependencyGraph;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  /** Why the list is shown instead of the map, if not by choice. */
  message: string | null;
  /** Extra controls at the end of the toolbar. */
  toolbarEnd?: ReactNode;
}

/**
 * Files grouped by module with their import counts. Used when the map
 * cannot be drawn, or when the user prefers a list. Every file stays
 * selectable, and the detail panel still links to its source.
 */
export function ListFallback({
  graph,
  selectedPath,
  onSelectFile,
  message,
  toolbarEnd,
}: ListFallbackProps) {
  const counts = useMemo(() => {
    const result = new Map<string, {imports: number; importedBy: number}>();
    for (const file of graph.files) {
      result.set(file.path, {imports: 0, importedBy: 0});
    }
    for (const edge of graph.edges) {
      const source = result.get(edge.source);
      const target = result.get(edge.target);
      if (source !== undefined) source.imports++;
      if (target !== undefined) target.importedBy++;
    }
    return result;
  }, [graph]);

  return (
    <div className="list-fallback">
      {toolbarEnd !== undefined && (
        <div className="list-fallback__toolbar">{toolbarEnd}</div>
      )}
      {message !== null && (
        <p className="list-fallback__message" role="status">
          {message}
        </p>
      )}
      {graph.modules.map(module => (
        <section key={module.id} className="list-fallback__module">
          <h3>{module.id === '.' ? module.name : module.id}</h3>
          <ul>
            {module.filePaths.map(path => {
              const count = counts.get(path);
              return (
                <li key={path}>
                  <button
                    type="button"
                    className="list-fallback__file"
                    aria-pressed={path === selectedPath}
                    onClick={() => onSelectFile(path)}
                  >
                    <code>{path.slice(path.lastIndexOf('/') + 1)}</code>
                    {count !== undefined && (
                      <span className="list-fallback__counts">
                        imports {count.imports} · imported by {count.importedBy}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

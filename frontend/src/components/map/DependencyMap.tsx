import type {NodeChange} from '@xyflow/react';
import {
  applyNodeChanges,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  useStoreApi,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type {ReactNode} from 'react';
import {useEffect, useId, useMemo, useRef, useState} from 'react';
import type {DependencyGraph} from '../../api/types.ts';
import {loadKeyOpen, saveKeyOpen} from '../../utils/mapKeyPreference.ts';
import type {MapActions} from './mapActions.ts';
import {MapActionsContext} from './mapActions.ts';
import {MapKey} from './MapKey.tsx';
import type {MapEdge, MapHighlight, MapNode} from './mapLayout.ts';
import {
  fileNodeId,
  focusGraph,
  groupNodeId,
  highlightAround,
  layoutMap,
  moduleNodeId,
  moduleIndex,
  neighborhood,
  unitFor,
} from './mapLayout.ts';
import {FileNode, ModuleGroupNode, ModuleNode} from './MapNodes.tsx';
import './DependencyMap.css';

/** The map must draw within this budget or the list view is shown. */
export const RENDER_BUDGET_MS = 2_000;

const NODE_TYPES = {
  module: ModuleNode,
  file: FileNode,
  moduleGroup: ModuleGroupNode,
};

const FIT_VIEW_OPTIONS = {padding: 0.15, maxZoom: 1.2};
/** The smallest zoom at which file names on the map can still be read. */
const READABLE_ZOOM = 0.75;
/** Room left above and beside a folder shown from its top-left corner. */
const FOLDER_MARGIN = 24;

interface DependencyMapProps {
  graph: DependencyGraph;
  expandedModules: ReadonlySet<string>;
  selectedPath: string | null;
  selectionRevision?: number;
  /** Files matching the current search, or null without a search. */
  matchedPaths: ReadonlySet<string> | null;
  /**
   * During a search, draw only the matching files (and the selected file)
   * instead of the whole repository.
   */
  matchesOnly?: boolean;
  onMatchesOnlyChange?: (matchesOnly: boolean) => void;
  /**
   * With a file selected, draw only it and the files it imports or is
   * imported by, instead of greying out the rest.
   */
  hideUnrelated?: boolean;
  onHideUnrelatedChange?: (hideUnrelated: boolean) => void;
  onSelectFile: (path: string) => void;
  onToggleModule: (moduleId: string, expanded?: boolean) => void;
  onCollapseAll: () => void;
  /** Called if the map has not drawn within RENDER_BUDGET_MS. */
  onTooSlow: () => void;
  /** Extra controls at the end of the toolbar. */
  toolbarEnd?: ReactNode;
}

/**
 * Interactive dependency map (Use Case 3). Modules start collapsed;
 * expanding one shows its files and the imports between them. Selecting a
 * file highlights what it imports and what imports it, and dims the rest.
 * Without a selection, files matching the search are highlighted instead
 * (Use Case 2). With `matchesOnly`, a search hides every other file; with
 * `hideUnrelated`, a selection hides every file it is not connected to.
 * Opening a folder zooms in on it.
 */
export function DependencyMap(props: DependencyMapProps) {
  return (
    <ReactFlowProvider>
      <MapCanvas {...props} />
    </ReactFlowProvider>
  );
}

function MapCanvas({
  graph,
  expandedModules,
  selectedPath,
  selectionRevision = 0,
  matchedPaths,
  matchesOnly = false,
  onMatchesOnlyChange,
  hideUnrelated = false,
  onHideUnrelatedChange,
  onSelectFile,
  onToggleModule,
  onCollapseAll,
  onTooSlow,
  toolbarEnd,
}: DependencyMapProps) {
  const flow = useReactFlow();
  const initialized = useNodesInitialized();
  const moduleOf = useMemo(() => moduleIndex(graph), [graph]);
  const searching = matchedPaths !== null;
  const hidingUnrelated =
    hideUnrelated && selectedPath !== null && moduleOf.has(selectedPath);
  // The files to draw when only part of the map is shown, as a stable key
  // so selecting another match does not lay the map out again.
  let focusKey: string | null = null;
  if (hidingUnrelated && selectedPath !== null) {
    focusKey = [...neighborhood(graph, selectedPath)].sort().join('\n');
  } else if (matchesOnly && searching) {
    focusKey = [
      ...matchedPaths,
      ...(matchedPaths.size === 0 || selectedPath === null
        ? []
        : [selectedPath]),
    ]
      .sort()
      .join('\n');
  }
  const focused = focusKey !== null;
  // When hiding unrelated files, only the selected file's own imports are
  // drawn: its importers left of it, what it imports right of it.
  const center = hidingUnrelated ? (selectedPath ?? undefined) : undefined;
  const shownGraph = useMemo(
    () =>
      focusKey === null
        ? graph
        : focusGraph(graph, new Set(focusKey.split('\n')), center),
    [graph, focusKey, center],
  );
  // Every module stays open when focused, so each match is its own node.
  const shownExpanded = useMemo(
    () =>
      focusKey === null
        ? expandedModules
        : new Set(shownGraph.modules.map(module => module.id)),
    [focusKey, expandedModules, shownGraph],
  );
  const layout = useMemo(
    () =>
      layoutMap(shownGraph, shownExpanded, {collapsible: focusKey === null}),
    [shownGraph, shownExpanded, focusKey],
  );
  // Positions the user dragged nodes to; reset whenever the layout changes.
  const [nodes, setNodes] = useState<MapNode[]>(layout.nodes);
  const [layoutShown, setLayoutShown] = useState(layout);
  if (layoutShown !== layout) {
    setLayoutShown(layout);
    setNodes(layout.nodes);
  }

  // Fall back to the list view if the nodes are not drawn in time, on
  // first render or after expanding a module. Background tabs do not draw,
  // so the clock only runs while the page is visible.
  useEffect(() => {
    if (initialized || layout.nodes.length === 0) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    function update() {
      if (document.visibilityState === 'visible') {
        timer ??= setTimeout(onTooSlow, RENDER_BUDGET_MS);
      } else {
        clearTimeout(timer);
        timer = undefined;
      }
    }
    update();
    document.addEventListener('visibilitychange', update);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', update);
    };
  }, [initialized, layout.nodes.length, onTooSlow]);

  const selectedUnit =
    selectedPath === null
      ? null
      : unitFor(selectedPath, moduleOf, shownExpanded);
  const selectedModuleId =
    selectedPath === null ? undefined : moduleOf.get(selectedPath);
  const selectedModuleIsCollapsed =
    focusKey === null &&
    selectedModuleId !== undefined &&
    !shownExpanded.has(selectedModuleId);
  const highlight = useMemo(
    () => highlightAround(layout.edges, selectedUnit),
    [layout.edges, selectedUnit],
  );
  // Search matches are highlighted only while nothing is selected.
  const matchedUnits = useMemo(() => {
    if (matchedPaths === null || selectedUnit !== null) return null;
    const units = new Set<string>();
    for (const path of matchedPaths) {
      const unit = unitFor(path, moduleOf, shownExpanded);
      if (unit !== null) units.add(unit);
    }
    return units;
  }, [matchedPaths, selectedUnit, moduleOf, shownExpanded]);

  const displayNodes = useMemo(
    () =>
      nodes.map(node => {
        let className = `map-node map-node--${node.type}`;
        if (highlight.selected !== null && node.type !== 'moduleGroup') {
          if (node.id === highlight.selected) {
            className += ' map-node--selected';
          } else if (highlight.related.has(node.id)) {
            className += ' map-node--related';
          } else {
            className += ' map-node--dimmed';
          }
        } else if (matchedUnits !== null && node.type !== 'moduleGroup') {
          className += matchedUnits.has(node.id)
            ? ' map-node--match'
            : ' map-node--dimmed';
        }
        return {...node, className};
      }),
    [nodes, highlight, matchedUnits],
  );

  const displayEdges = useMemo(
    () =>
      layout.edges.map(edge => ({
        ...edge,
        className: edgeClass(edge, highlight, matchedUnits),
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 24,
          height: 24,
          color: edgeColor(edge, highlight),
        },
      })),
    [layout.edges, highlight, matchedUnits],
  );

  // The folder the user just opened on the map, to zoom in on once its
  // files are drawn.
  const zoomToModule = useRef<string | null>(null);

  // Bring the selected file into view, e.g. when chosen in the explorer.
  // Not while zooming to a folder or while only its neighbors are drawn:
  // then the whole view is fitted instead.
  useEffect(() => {
    if (
      selectedPath === null ||
      !initialized ||
      hidingUnrelated ||
      zoomToModule.current !== null
    ) {
      return;
    }
    const moduleId = moduleOf.get(selectedPath);
    const node =
      flow.getInternalNode(fileNodeId(selectedPath)) ??
      (moduleId === undefined
        ? undefined
        : flow.getInternalNode(moduleNodeId(moduleId)));
    if (node === undefined) return;
    const {x, y} = node.internals.positionAbsolute;
    void flow.setCenter(
      x + (node.measured.width ?? 0) / 2,
      y + (node.measured.height ?? 0) / 2,
      {zoom: Math.max(flow.getZoom(), 0.8), duration: 300},
    );
  }, [
    selectedPath,
    selectionRevision,
    initialized,
    layout,
    flow,
    moduleOf,
    hidingUnrelated,
  ]);

  // Fit an opened folder on screen. A folder too big to fit at a readable
  // size is shown at the smallest readable zoom from its leftmost file
  // (importers sit left of what they import, so that is where reading
  // starts); the rest is a drag away.
  const store = useStoreApi();
  function zoomToFolder(groupId: string) {
    const node = flow.getInternalNode(groupId);
    const {width: paneWidth, height: paneHeight} = store.getState();
    if (node === undefined) return;
    const width = node.measured.width ?? 0;
    const height = node.measured.height ?? 0;
    const fitZoom = Math.min(
      (paneWidth * (1 - 2 * FIT_VIEW_OPTIONS.padding)) / width,
      (paneHeight * (1 - 2 * FIT_VIEW_OPTIONS.padding)) / height,
    );
    if (fitZoom >= READABLE_ZOOM) {
      void flow.fitView({
        ...FIT_VIEW_OPTIONS,
        nodes: [{id: groupId}],
        duration: 300,
      });
      return;
    }
    let first: {x: number; y: number; height: number} | null = null;
    for (const child of layout.nodes) {
      if (child.parentId !== groupId) continue;
      const placed = flow.getInternalNode(child.id);
      if (placed === undefined) continue;
      const {x, y} = placed.internals.positionAbsolute;
      if (first === null || x < first.x || (x === first.x && y < first.y)) {
        first = {x, y, height: placed.measured.height ?? 0};
      }
    }
    const anchor = first ?? {...node.internals.positionAbsolute, height: 0};
    void flow.setViewport(
      {
        x: FOLDER_MARGIN - anchor.x * READABLE_ZOOM,
        y: paneHeight / 2 - (anchor.y + anchor.height / 2) * READABLE_ZOOM,
        zoom: READABLE_ZOOM,
      },
      {duration: 300},
    );
  }

  // When the map's shape changes: zoom in on a folder that was just
  // opened, otherwise fit everything drawn (unless a file is selected on
  // the full map, which the effect above brings into view).
  useEffect(() => {
    if (!initialized) return;
    const moduleId = zoomToModule.current;
    if (moduleId !== null) {
      const groupId = groupNodeId(moduleId);
      if (layout.nodes.some(node => node.id === groupId)) {
        // Wait until the folder's box has been drawn and measured.
        if (flow.getInternalNode(groupId)?.measured.width === undefined) {
          return;
        }
        zoomToModule.current = null;
        zoomToFolder(groupId);
        return;
      }
      zoomToModule.current = null;
    }
    if (selectedPath === null || hidingUnrelated) {
      void flow.fitView({...FIT_VIEW_OPTIONS, duration: 200});
    }
    // Only on layout changes, not on every selection change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, initialized]);

  const actions = useMemo<MapActions>(
    () => ({
      selectFile: onSelectFile,
      toggleModule(moduleId, expanded) {
        if (expanded === true) zoomToModule.current = moduleId;
        onToggleModule(moduleId, expanded);
      },
    }),
    [onSelectFile, onToggleModule],
  );

  const keyId = useId();
  const [keyOpen, setKeyOpen] = useState(loadKeyOpen);
  function showKey(open: boolean) {
    setKeyOpen(open);
    saveKeyOpen(open);
  }

  function resetView() {
    setNodes(layout.nodes);
    requestAnimationFrame(
      () => void flow.fitView({...FIT_VIEW_OPTIONS, duration: 300}),
    );
  }

  return (
    <MapActionsContext value={actions}>
      <div className="map">
        <div className="map__toolbar" role="toolbar" aria-label="Map controls">
          <div className="map__group" role="group" aria-label="Zoom">
            <button
              type="button"
              className="button"
              onClick={() => void flow.zoomOut({duration: 200})}
              aria-label="Zoom out"
              title="Zoom out"
            >
              −
            </button>
            <button
              type="button"
              className="button"
              onClick={() => void flow.zoomIn({duration: 200})}
              aria-label="Zoom in"
              title="Zoom in"
            >
              +
            </button>
            <button
              type="button"
              className="button"
              onClick={resetView}
              title="Fit the whole map on screen and undo any dragging"
            >
              Fit
            </button>
          </div>
          {!focused && (
            <button type="button" className="button" onClick={onCollapseAll}>
              Collapse all
            </button>
          )}
          {searching && onMatchesOnlyChange !== undefined && (
            <label className="map__toggle">
              <input
                type="checkbox"
                checked={matchesOnly}
                onChange={event => onMatchesOnlyChange(event.target.checked)}
              />
              Only show matches
            </label>
          )}
          {selectedPath !== null && onHideUnrelatedChange !== undefined && (
            <label
              className="map__toggle"
              title="Show only the selected file and the files it imports or is imported by"
            >
              <input
                type="checkbox"
                checked={hideUnrelated}
                onChange={event => onHideUnrelatedChange(event.target.checked)}
              />
              Hide unrelated files
            </label>
          )}
          <button
            type="button"
            className="button"
            aria-expanded={keyOpen}
            aria-controls={keyId}
            onClick={() => showKey(!keyOpen)}
            title="What the boxes, colors and lines mean"
          >
            Key
          </button>
          {toolbarEnd}
        </div>
        {selectedModuleIsCollapsed && selectedPath !== null && (
          <p className="map__selection-hint" role="status">
            Inside <code>{selectedModuleId}/</code> (collapsed). Expand to see{' '}
            <code>{selectedPath}</code>.
          </p>
        )}
        <div className="map__canvas">
          {focused && layout.nodes.length === 0 && (
            <p role="status">No matching files to show on the map.</p>
          )}
          {keyOpen && <MapKey id={keyId} onClose={() => showKey(false)} />}
          <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            nodeTypes={NODE_TYPES}
            onNodesChange={(changes: NodeChange<MapNode>[]) =>
              setNodes(current => applyNodeChanges(changes, current))
            }
            fitView
            fitViewOptions={FIT_VIEW_OPTIONS}
            minZoom={0.1}
            nodesConnectable={false}
            nodesFocusable={false}
            edgesFocusable={false}
            elementsSelectable={false}
            colorMode="system"
            proOptions={{hideAttribution: true}}
          />
        </div>
      </div>
    </MapActionsContext>
  );
}

function edgeClass(
  edge: MapEdge,
  highlight: MapHighlight,
  matchedUnits: ReadonlySet<string> | null,
): string {
  if (highlight.selected !== null) {
    if (!highlight.edges.has(edge.id)) return 'map-edge map-edge--dimmed';
    return edge.source === highlight.selected
      ? 'map-edge map-edge--imports'
      : 'map-edge map-edge--imported-by';
  }
  if (matchedUnits !== null) {
    return matchedUnits.has(edge.source) && matchedUnits.has(edge.target)
      ? 'map-edge map-edge--highlighted'
      : 'map-edge map-edge--dimmed';
  }
  return 'map-edge';
}

function edgeColor(edge: MapEdge, highlight: MapHighlight): string {
  if (highlight.selected === null || !highlight.edges.has(edge.id)) {
    return 'var(--color-muted)';
  }
  return edge.source === highlight.selected
    ? 'var(--map-imports-color)'
    : 'var(--map-imported-by-color)';
}

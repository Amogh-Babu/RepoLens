import type {NodeChange} from '@xyflow/react';
import {
  applyNodeChanges,
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type {ReactNode} from 'react';
import {useEffect, useMemo, useState} from 'react';
import type {DependencyGraph} from '../../api/types.ts';
import type {MapActions} from './mapActions.ts';
import {MapActionsContext} from './mapActions.ts';
import type {MapEdge, MapHighlight, MapNode} from './mapLayout.ts';
import {
  fileNodeId,
  highlightAround,
  layoutMap,
  moduleIndex,
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

interface DependencyMapProps {
  graph: DependencyGraph;
  expandedModules: ReadonlySet<string>;
  selectedPath: string | null;
  /** Files matching the current search, or null without a search. */
  matchedPaths: ReadonlySet<string> | null;
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
 * (Use Case 2).
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
  matchedPaths,
  onSelectFile,
  onToggleModule,
  onCollapseAll,
  onTooSlow,
  toolbarEnd,
}: DependencyMapProps) {
  const flow = useReactFlow();
  const initialized = useNodesInitialized();
  const layout = useMemo(
    () => layoutMap(graph, expandedModules),
    [graph, expandedModules],
  );
  const moduleOf = useMemo(() => moduleIndex(graph), [graph]);
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
    if (initialized) return;
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
  }, [initialized, onTooSlow]);

  const selectedUnit =
    selectedPath === null
      ? null
      : unitFor(selectedPath, moduleOf, expandedModules);
  const highlight = useMemo(
    () => highlightAround(layout.edges, selectedUnit),
    [layout.edges, selectedUnit],
  );
  // Search matches are highlighted only while nothing is selected.
  const matchedUnits = useMemo(() => {
    if (matchedPaths === null || selectedUnit !== null) return null;
    const units = new Set<string>();
    for (const path of matchedPaths) {
      const unit = unitFor(path, moduleOf, expandedModules);
      if (unit !== null) units.add(unit);
    }
    return units;
  }, [matchedPaths, selectedUnit, moduleOf, expandedModules]);

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
      })),
    [layout.edges, highlight, matchedUnits],
  );

  // Bring the selected file into view, e.g. when chosen in the explorer.
  useEffect(() => {
    if (selectedPath === null || !initialized) return;
    const node = flow.getInternalNode(fileNodeId(selectedPath));
    if (node === undefined) return;
    const {x, y} = node.internals.positionAbsolute;
    void flow.setCenter(
      x + (node.measured.width ?? 0) / 2,
      y + (node.measured.height ?? 0) / 2,
      {zoom: Math.max(flow.getZoom(), 0.8), duration: 300},
    );
  }, [selectedPath, initialized, layout, flow]);

  // Fit the whole map whenever its shape changes.
  useEffect(() => {
    if (initialized && selectedPath === null) {
      void flow.fitView({...FIT_VIEW_OPTIONS, duration: 200});
    }
    // Only on layout changes, not on every selection change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, initialized]);

  const actions = useMemo<MapActions>(
    () => ({selectFile: onSelectFile, toggleModule: onToggleModule}),
    [onSelectFile, onToggleModule],
  );

  function resetView() {
    setNodes(layout.nodes);
    requestAnimationFrame(
      () => void flow.fitView({...FIT_VIEW_OPTIONS, duration: 300}),
    );
  }

  return (
    <MapActionsContext value={actions}>
      <div className="map">
        <div className="map__toolbar">
          <button type="button" className="button" onClick={resetView}>
            Reset view
          </button>
          <button type="button" className="button" onClick={onCollapseAll}>
            Collapse all
          </button>
          <span className="map__legend">
            Arrows point from a file to what it imports.
          </span>
          {toolbarEnd}
        </div>
        <div className="map__canvas">
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
          >
            <Background gap={24} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
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
    return highlight.edges.has(edge.id)
      ? 'map-edge map-edge--highlighted'
      : 'map-edge map-edge--dimmed';
  }
  if (matchedUnits !== null) {
    return matchedUnits.has(edge.source) && matchedUnits.has(edge.target)
      ? 'map-edge map-edge--highlighted'
      : 'map-edge map-edge--dimmed';
  }
  return 'map-edge';
}

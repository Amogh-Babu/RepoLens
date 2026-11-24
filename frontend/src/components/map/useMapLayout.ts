import {useEffect, useMemo, useRef, useState} from 'react';
import type {DependencyGraph} from '../../api/types.ts';
import type {MapLayout} from './mapLayout.ts';
import {layoutMap} from './mapLayout.ts';
import type {LayoutRequest, LayoutResponse} from './mapLayout.worker.ts';

export const LAYOUT_TIMEOUT_MS = 10_000;
const CACHED_LAYOUTS_PER_GRAPH = 24;

export type MapLayoutState =
  | {status: 'ready'; layout: MapLayout}
  | {status: 'pending'; previous: MapLayout | null}
  | {status: 'failed'; reason: 'timeout' | 'error'};

export type LayoutWorkerFactory = (() => Worker) | null;

const DEFAULT_WORKER_FACTORY: LayoutWorkerFactory =
  typeof Worker === 'undefined'
    ? null
    : () =>
        new Worker(new URL('./mapLayout.worker.ts', import.meta.url), {
          type: 'module',
        });

const layoutCache = new WeakMap<DependencyGraph, Map<string, MapLayout>>();

function layoutKey(expanded: ReadonlySet<string>, collapsible: boolean) {
  return JSON.stringify([collapsible, [...expanded].sort()]);
}

function parseLayoutKey(key: string): [boolean, Set<string>] {
  const [collapsible, expanded] = JSON.parse(key) as [boolean, string[]];
  return [collapsible, new Set(expanded)];
}

function readCached(graph: DependencyGraph, key: string) {
  return layoutCache.get(graph)?.get(key);
}

function cacheLayout(graph: DependencyGraph, key: string, layout: MapLayout) {
  let entries = layoutCache.get(graph);
  if (entries === undefined) {
    entries = new Map();
    layoutCache.set(graph, entries);
  }
  entries.set(key, layout);
  if (entries.size > CACHED_LAYOUTS_PER_GRAPH) {
    entries.delete(entries.keys().next().value as string);
  }
}

interface SettledLayout {
  graph: DependencyGraph;
  key: string;
  state: MapLayoutState;
}

/**
 * Runs Dagre away from the UI thread. Every request owns a worker so changing
 * the graph or expanded folders can terminate stale CPU work immediately.
 */
export function useMapLayout(
  graph: DependencyGraph,
  expanded: ReadonlySet<string>,
  collapsible: boolean,
  {
    createWorker = DEFAULT_WORKER_FACTORY,
    timeoutMs = LAYOUT_TIMEOUT_MS,
  }: {createWorker?: LayoutWorkerFactory; timeoutMs?: number} = {},
): MapLayoutState {
  const key = layoutKey(expanded, collapsible);
  const synchronous = createWorker === null;
  const synchronousLayout = useMemo(() => {
    if (!synchronous) return null;
    const cached = readCached(graph, key);
    if (cached !== undefined) return cached;
    const [isCollapsible, open] = parseLayoutKey(key);
    const layout = layoutMap(graph, open, {collapsible: isCollapsible});
    cacheLayout(graph, key, layout);
    return layout;
  }, [graph, key, synchronous]);
  const cached = synchronous ? undefined : readCached(graph, key);
  const [settled, setSettled] = useState<SettledLayout | null>(null);
  const nextRequest = useRef(0);

  useEffect(() => {
    if (createWorker === null || cached !== undefined) return;
    const worker = createWorker();
    const id = ++nextRequest.current;
    let active = true;

    const finish = (state: MapLayoutState) => {
      if (!active) return;
      active = false;
      clearTimeout(timer);
      worker.terminate();
      setSettled({graph, key, state});
    };
    const timer = setTimeout(
      () => finish({status: 'failed', reason: 'timeout'}),
      timeoutMs,
    );
    worker.onmessage = (event: MessageEvent<LayoutResponse>) => {
      if (!active || event.data.id !== id) return;
      if ('error' in event.data) {
        console.error(
          'The dependency map could not be laid out',
          event.data.error,
        );
        finish({status: 'failed', reason: 'error'});
        return;
      }
      cacheLayout(graph, key, event.data.layout);
      finish({status: 'ready', layout: event.data.layout});
    };
    worker.onerror = event => {
      event.preventDefault();
      finish({status: 'failed', reason: 'error'});
    };
    const [isCollapsible, open] = parseLayoutKey(key);
    const request: LayoutRequest = {
      id,
      graph,
      expanded: [...open],
      collapsible: isCollapsible,
    };
    worker.postMessage(request);

    return () => {
      clearTimeout(timer);
      if (active) worker.terminate();
      active = false;
    };
  }, [cached, createWorker, graph, key, timeoutMs]);

  if (synchronousLayout !== null) {
    return {status: 'ready', layout: synchronousLayout};
  }
  if (cached !== undefined) return {status: 'ready', layout: cached};
  if (settled?.graph === graph && settled.key === key) return settled.state;
  const previous =
    settled?.graph === graph && settled.state.status === 'ready'
      ? settled.state.layout
      : null;
  return {status: 'pending', previous};
}

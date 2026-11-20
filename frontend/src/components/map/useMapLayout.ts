import {useEffect, useMemo, useRef, useState} from 'react';
import type {DependencyGraph} from '../../api/types.ts';
import type {MapLayout} from './mapLayout.ts';
import {layoutMap} from './mapLayout.ts';
import type {LayoutRequest, LayoutResponse} from './mapLayout.worker.ts';

/** A layout still running after this long is stopped and the list shown. */
export const LAYOUT_TIMEOUT_MS = 10_000;

/** Layouts kept per graph, so closing and reopening a folder is instant. */
const CACHED_LAYOUTS_PER_GRAPH = 24;

export type MapLayoutState =
  | {status: 'ready'; layout: MapLayout}
  /** `previous` is the last layout of the same graph, shown meanwhile. */
  | {status: 'pending'; previous: MapLayout | null}
  | {status: 'failed'; reason: 'timeout' | 'error'};

/** Creates the layout worker, or null to lay out on the main thread. */
export type LayoutWorkerFactory = (() => Worker) | null;

const DEFAULT_WORKER_FACTORY: LayoutWorkerFactory =
  typeof Worker === 'undefined'
    ? null
    : () =>
        new Worker(new URL('./mapLayout.worker.ts', import.meta.url), {
          type: 'module',
        });

// Dropped with the graph, so another repository's layouts are not kept.
const layoutCache = new WeakMap<DependencyGraph, Map<string, MapLayout>>();

function cachedLayout(
  graph: DependencyGraph,
  key: string,
): MapLayout | undefined {
  const layouts = layoutCache.get(graph);
  const layout = layouts?.get(key);
  if (layouts !== undefined && layout !== undefined) {
    // Most recently used last.
    layouts.delete(key);
    layouts.set(key, layout);
  }
  return layout;
}

function remember(graph: DependencyGraph, key: string, layout: MapLayout) {
  let layouts = layoutCache.get(graph);
  if (layouts === undefined) {
    layouts = new Map();
    layoutCache.set(graph, layouts);
  }
  layouts.set(key, layout);
  if (layouts.size > CACHED_LAYOUTS_PER_GRAPH) {
    layouts.delete(layouts.keys().next().value as string);
  }
}

function layoutKey(expanded: ReadonlySet<string>, collapsible: boolean) {
  return JSON.stringify([collapsible, [...expanded].sort()]);
}

function parseKey(key: string): [boolean, Set<string>] {
  const [collapsible, expanded] = JSON.parse(key) as [boolean, string[]];
  return [collapsible, new Set(expanded)];
}

interface Settled {
  graph: DependencyGraph;
  key: string;
  state: MapLayoutState;
}

/**
 * Lays out the map in a Web Worker. Only the latest request counts: a
 * newer one, a different graph, or unmounting stops a layout still running
 * (by ending its worker, since a layout cannot be interrupted), and a late
 * answer to an old request is ignored. A layout that runs past
 * `timeoutMs` is stopped and reported as failed. Without Worker support
 * (as in tests) the layout runs on the main thread.
 */
export function useMapLayout(
  graph: DependencyGraph,
  expanded: ReadonlySet<string>,
  collapsible: boolean,
  {
    createWorker = DEFAULT_WORKER_FACTORY,
    timeoutMs = LAYOUT_TIMEOUT_MS,
    enabled = true,
  }: {
    createWorker?: LayoutWorkerFactory;
    timeoutMs?: number;
    /** False lays nothing out, e.g. for a map too large to draw. */
    enabled?: boolean;
  } = {},
): MapLayoutState {
  const key = layoutKey(expanded, collapsible);
  const synchronous = createWorker === null;
  const syncLayout = useMemo(() => {
    if (!synchronous || !enabled) return null;
    const cached = cachedLayout(graph, key);
    if (cached !== undefined) return cached;
    const [isCollapsible, open] = parseKey(key);
    const layout = layoutMap(graph, open, {collapsible: isCollapsible});
    remember(graph, key, layout);
    return layout;
  }, [synchronous, enabled, graph, key]);

  const cached = synchronous || !enabled ? undefined : cachedLayout(graph, key);
  const [settled, setSettled] = useState<Settled | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    if (createWorker === null || !enabled || cached !== undefined) return;
    const id = ++latestRequest.current;
    const worker = workerRef.current ?? createWorker();
    workerRef.current = worker;
    let done = false;
    function stopWorker() {
      worker.terminate();
      if (workerRef.current === worker) workerRef.current = null;
    }
    function finish(state: MapLayoutState) {
      done = true;
      clearTimeout(timer);
      setSettled({graph, key, state});
    }
    const timer = setTimeout(() => {
      stopWorker();
      finish({status: 'failed', reason: 'timeout'});
    }, timeoutMs);
    worker.onmessage = (event: MessageEvent<LayoutResponse>) => {
      if (done || event.data.id !== latestRequest.current) return;
      if ('error' in event.data) {
        console.error(
          'The dependency map could not be laid out',
          event.data.error,
        );
        finish({status: 'failed', reason: 'error'});
        return;
      }
      remember(graph, key, event.data.layout);
      finish({status: 'ready', layout: event.data.layout});
    };
    worker.onerror = event => {
      if (done) return;
      event.preventDefault();
      stopWorker();
      finish({status: 'failed', reason: 'error'});
    };
    const [isCollapsible, open] = parseKey(key);
    const request: LayoutRequest = {
      id,
      graph,
      expanded: [...open],
      collapsible: isCollapsible,
    };
    worker.postMessage(request);
    return () => {
      clearTimeout(timer);
      // Superseded or unmounted while still laying out: stop the work.
      if (!done) stopWorker();
      done = true;
    };
  }, [createWorker, enabled, cached, graph, key, timeoutMs]);

  // End the worker with the map.
  useEffect(
    () => () => {
      workerRef.current?.terminate();
      workerRef.current = null;
    },
    [],
  );

  if (syncLayout !== null) return {status: 'ready', layout: syncLayout};
  if (cached !== undefined) return {status: 'ready', layout: cached};
  if (settled !== null && settled.graph === graph && settled.key === key) {
    return settled.state;
  }
  const previous =
    settled !== null &&
    settled.graph === graph &&
    settled.state.status === 'ready'
      ? settled.state.layout
      : null;
  return {status: 'pending', previous};
}

import {act, renderHook} from '@testing-library/react';
import type {DependencyGraph} from '../../api/types.ts';
import {layoutMap} from './mapLayout.ts';
import type {LayoutRequest, LayoutResponse} from './mapLayout.worker.ts';
import {LAYOUT_TIMEOUT_MS, useMapLayout} from './useMapLayout.ts';

const GRAPH: DependencyGraph = {
  modules: [
    {id: 'app', name: 'app', filePaths: ['app/a.py', 'app/b.py']},
    {id: 'lib', name: 'lib', filePaths: ['lib/c.py']},
  ],
  files: [
    {path: 'app/a.py', module: 'app', parsed: true, lineCount: 1},
    {path: 'app/b.py', module: 'app', parsed: true, lineCount: 1},
    {path: 'lib/c.py', module: 'lib', parsed: true, lineCount: 1},
  ],
  edges: [
    {source: 'app/a.py', target: 'app/b.py'},
    {source: 'app/b.py', target: 'lib/c.py'},
  ],
};

/** A stand-in Worker: the test answers its requests by hand. */
class FakeWorker {
  static created: FakeWorker[] = [];
  requests: LayoutRequest[] = [];
  terminated = false;
  onmessage: ((event: MessageEvent<LayoutResponse>) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;

  constructor() {
    FakeWorker.created.push(this);
  }

  postMessage(request: LayoutRequest) {
    this.requests.push(request);
  }

  terminate() {
    this.terminated = true;
  }

  /** Lays out request `index` for real and answers it. */
  answer(index = this.requests.length - 1) {
    const request = at(this.requests, index);
    const layout = layoutMap(request.graph, new Set(request.expanded), {
      collapsible: request.collapsible,
    });
    act(() =>
      this.onmessage?.({
        data: {id: request.id, layout},
      } as MessageEvent<LayoutResponse>),
    );
  }
}

const createWorker = () => new FakeWorker() as unknown as Worker;

/** Item `index` of `items`, failing the test if there is none. */
function at<T>(items: T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`No item ${index}`);
  return item;
}

function graphCopy(): DependencyGraph {
  // A fresh object, so no layout of it is cached from another test.
  return structuredClone(GRAPH);
}

beforeEach(() => {
  FakeWorker.created = [];
});

describe('useMapLayout', () => {
  it('lays out in a worker and reports the result', () => {
    const graph = graphCopy();
    const {result} = renderHook(() =>
      useMapLayout(graph, new Set(['app']), true, {createWorker}),
    );

    expect(result.current).toEqual({status: 'pending', previous: null});
    const worker = at(FakeWorker.created, 0);
    expect(at(worker.requests, 0)).toMatchObject({
      graph,
      expanded: ['app'],
      collapsible: true,
    });

    worker.answer();

    expect(result.current.status).toBe('ready');
    if (result.current.status !== 'ready') return;
    expect(result.current.layout.nodes.map(node => node.id)).toContain(
      'file:app/a.py',
    );
  });

  it('stops a superseded layout and ignores its late answer', () => {
    const graph = graphCopy();
    const {result, rerender} = renderHook(
      ({expanded}: {expanded: Set<string>}) =>
        useMapLayout(graph, expanded, true, {createWorker}),
      {initialProps: {expanded: new Set<string>()}},
    );
    const first = at(FakeWorker.created, 0);

    rerender({expanded: new Set(['app'])});

    // The first layout was still running, so its worker was ended...
    expect(first.terminated).toBe(true);
    const second = at(FakeWorker.created, 1);
    expect(at(second.requests, 0).expanded).toEqual(['app']);
    // ...and an answer that arrives anyway is ignored.
    first.answer();
    expect(result.current.status).toBe('pending');

    second.answer();
    expect(result.current.status).toBe('ready');
  });

  it('ignores an answer to an older request on the same worker', () => {
    const graph = graphCopy();
    const {result, rerender} = renderHook(
      ({expanded}: {expanded: Set<string>}) =>
        useMapLayout(graph, expanded, true, {createWorker}),
      {initialProps: {expanded: new Set<string>()}},
    );
    const worker = at(FakeWorker.created, 0);
    worker.answer(); // settle the first request so the worker is kept
    rerender({expanded: new Set(['app'])});
    expect(worker.requests).toHaveLength(2);

    // Replay the answer to request 1 while request 2 is pending.
    worker.answer(0);

    expect(result.current.status).toBe('pending');
    if (result.current.status !== 'pending') return;
    // The map keeps showing the last layout meanwhile.
    expect(result.current.previous).not.toBeNull();
  });

  it('stops a layout that runs too long', () => {
    vi.useFakeTimers();
    try {
      const graph = graphCopy();
      const {result} = renderHook(() =>
        useMapLayout(graph, new Set(), true, {createWorker}),
      );

      act(() => vi.advanceTimersByTime(LAYOUT_TIMEOUT_MS - 1));
      expect(result.current.status).toBe('pending');
      act(() => vi.advanceTimersByTime(1));

      expect(result.current).toEqual({status: 'failed', reason: 'timeout'});
      expect(at(FakeWorker.created, 0).terminated).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it('reports a layout that throws', () => {
    const graph = graphCopy();
    const {result} = renderHook(() =>
      useMapLayout(graph, new Set(), true, {createWorker}),
    );
    const worker = at(FakeWorker.created, 0);
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});

    act(() =>
      worker.onmessage?.({
        data: {id: at(worker.requests, 0).id, error: 'Not possible'},
      } as MessageEvent<LayoutResponse>),
    );

    expect(result.current).toEqual({status: 'failed', reason: 'error'});
    error.mockRestore();
  });

  it('ends the worker when the map goes away', () => {
    const {unmount} = renderHook(() =>
      useMapLayout(graphCopy(), new Set(), true, {createWorker}),
    );
    const worker = at(FakeWorker.created, 0);
    worker.answer();

    unmount();

    expect(worker.terminated).toBe(true);
  });

  it('starts over for another repository', () => {
    const {result, rerender} = renderHook(
      ({graph}: {graph: DependencyGraph}) =>
        useMapLayout(graph, new Set(), true, {createWorker}),
      {initialProps: {graph: graphCopy()}},
    );
    at(FakeWorker.created, 0).answer();

    rerender({graph: graphCopy()});

    // Another repository's map is never shown meanwhile.
    expect(result.current).toEqual({status: 'pending', previous: null});
  });

  it('reuses layouts when modules are opened and closed again', () => {
    const graph = graphCopy();
    const {result, rerender} = renderHook(
      ({expanded}: {expanded: Set<string>}) =>
        useMapLayout(graph, expanded, true, {createWorker}),
      {initialProps: {expanded: new Set<string>()}},
    );
    const worker = at(FakeWorker.created, 0);
    worker.answer();
    rerender({expanded: new Set(['app'])});
    worker.answer();

    for (let i = 0; i < 5; i++) {
      rerender({expanded: new Set()});
      expect(result.current.status).toBe('ready');
      rerender({expanded: new Set(['app'])});
      expect(result.current.status).toBe('ready');
    }

    // Two layouts made, once each, by one worker.
    expect(FakeWorker.created).toHaveLength(1);
    expect(worker.requests).toHaveLength(2);
  });

  it('lays out nothing when disabled', () => {
    const {result} = renderHook(() =>
      useMapLayout(graphCopy(), new Set(), true, {
        createWorker,
        enabled: false,
      }),
    );

    expect(FakeWorker.created).toHaveLength(0);
    expect(result.current.status).toBe('pending');
  });

  it('lays out on the main thread without Worker support', () => {
    const {result} = renderHook(() =>
      useMapLayout(graphCopy(), new Set(['lib']), false, {createWorker: null}),
    );

    expect(result.current.status).toBe('ready');
  });
});

import {act, renderHook} from '@testing-library/react';
import type {DependencyGraph} from '../../api/types.ts';
import {layoutMap} from './mapLayout.ts';
import type {LayoutRequest, LayoutResponse} from './mapLayout.worker.ts';
import {LAYOUT_TIMEOUT_MS, useMapLayout} from './useMapLayout.ts';

const GRAPH: DependencyGraph = {
  modules: [{id: 'app', name: 'app', filePaths: ['app/a.py']}],
  files: [{path: 'app/a.py', module: 'app', parsed: true, lineCount: 1}],
  edges: [],
};

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

  answer(index = this.requests.length - 1) {
    const request = this.requests[index];
    if (request === undefined) throw new Error(`No request ${index}`);
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
const graphCopy = () => structuredClone(GRAPH);

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
    const worker = FakeWorker.created[0];
    expect(worker?.requests[0]).toMatchObject({
      graph,
      expanded: ['app'],
      collapsible: true,
    });

    worker?.answer();

    expect(result.current.status).toBe('ready');
  });

  it('terminates a superseded layout and ignores its late answer', () => {
    const graph = graphCopy();
    const {result, rerender} = renderHook(
      ({expanded}: {expanded: Set<string>}) =>
        useMapLayout(graph, expanded, true, {createWorker}),
      {initialProps: {expanded: new Set<string>()}},
    );
    const first = FakeWorker.created[0];

    rerender({expanded: new Set(['app'])});

    expect(first?.terminated).toBe(true);
    expect(FakeWorker.created[1]?.requests[0]?.expanded).toEqual(['app']);
    first?.answer();
    expect(result.current.status).toBe('pending');
    FakeWorker.created[1]?.answer();
    expect(result.current.status).toBe('ready');
  });

  it('terminates a layout that exceeds the timeout', () => {
    vi.useFakeTimers();
    try {
      const graph = graphCopy();
      const {result} = renderHook(() =>
        useMapLayout(graph, new Set(), true, {createWorker}),
      );

      act(() => vi.advanceTimersByTime(LAYOUT_TIMEOUT_MS));

      expect(result.current).toEqual({status: 'failed', reason: 'timeout'});
      expect(FakeWorker.created[0]?.terminated).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it('terminates the active worker on unmount', () => {
    const {unmount} = renderHook(() =>
      useMapLayout(graphCopy(), new Set(), true, {createWorker}),
    );
    const worker = FakeWorker.created[0];

    unmount();

    expect(worker?.terminated).toBe(true);
  });

  it('does not start a worker when disabled and stops an active layout', () => {
    const graph = graphCopy();
    const {rerender} = renderHook(
      ({enabled}: {enabled: boolean}) =>
        useMapLayout(graph, new Set(), true, {createWorker, enabled}),
      {initialProps: {enabled: false}},
    );

    expect(FakeWorker.created).toHaveLength(0);
    rerender({enabled: true});
    expect(FakeWorker.created).toHaveLength(1);
    rerender({enabled: false});
    expect(FakeWorker.created[0]?.terminated).toBe(true);
  });
});

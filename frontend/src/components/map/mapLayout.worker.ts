/// <reference lib="webworker" />
/**
 * Lays out the dependency map off the main thread, so a large layout never
 * freezes the page. See `useMapLayout`.
 */
import type {DependencyGraph} from '../../api/types.ts';
import {layoutMap} from './mapLayout.ts';

export interface LayoutRequest {
  id: number;
  graph: DependencyGraph;
  expanded: string[];
  collapsible: boolean;
}

export type LayoutResponse =
  | {id: number; layout: ReturnType<typeof layoutMap>}
  | {id: number; error: string};

self.onmessage = (event: MessageEvent<LayoutRequest>) => {
  const {id, graph, expanded, collapsible} = event.data;
  let response: LayoutResponse;
  try {
    response = {id, layout: layoutMap(graph, new Set(expanded), {collapsible})};
  } catch (error) {
    response = {id, error: String(error)};
  }
  self.postMessage(response);
};

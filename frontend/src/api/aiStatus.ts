import type {ApiClient} from './client.ts';
import type {AiStatus} from './types.ts';

const statusRequests = new WeakMap<ApiClient, Promise<AiStatus>>();

/**
 * GET /ai/status, fetched once per client and shared by every AI section.
 * A failed request is forgotten, so the next caller tries again.
 */
export function loadAiStatus(api: ApiClient): Promise<AiStatus> {
  let request = statusRequests.get(api);
  if (request === undefined) {
    request = api.getAiStatus();
    request.catch(() => statusRequests.delete(api));
    statusRequests.set(api, request);
  }
  return request;
}

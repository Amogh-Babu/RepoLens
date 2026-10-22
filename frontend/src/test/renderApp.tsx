import {render} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {ApiClientContext} from '../api/apiClientContext.ts';
import type {ApiClient} from '../api/client.ts';
import {MockApiClient} from '../api/mock/mockClient.ts';
import {App} from '../App.tsx';

/**
 * Renders the whole app at `path`, with a mock API client that answers
 * immediately unless another client is given.
 */
export function renderApp(
  path: string,
  client: ApiClient = new MockApiClient({latencyMs: 0}),
) {
  return render(
    <ApiClientContext value={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </ApiClientContext>,
  );
}

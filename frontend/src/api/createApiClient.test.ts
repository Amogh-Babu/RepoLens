import {HttpApiClient} from './client.ts';
import {createApiClient} from './createApiClient.ts';
import {MockApiClient} from './mock/mockClient.ts';

describe('createApiClient', () => {
  it('uses the mock client by default', () => {
    expect(createApiClient({})).toBeInstanceOf(MockApiClient);
  });

  it('uses the HTTP client in http mode', () => {
    expect(createApiClient({VITE_API_MODE: 'http'})).toBeInstanceOf(
      HttpApiClient,
    );
  });

  it('rejects an unknown mode', () => {
    expect(() => createApiClient({VITE_API_MODE: 'graphql'})).toThrow(
      /Unknown VITE_API_MODE/,
    );
  });
});

import {HttpApiClient} from './client.ts';
import {createApiClient} from './createApiClient.ts';
import {MockApiClient} from './mock/mockClient.ts';

describe('createApiClient', () => {
  it('uses the HTTP client by default', () => {
    expect(createApiClient({})).toBeInstanceOf(HttpApiClient);
    expect(createApiClient({VITE_API_MODE: ''})).toBeInstanceOf(HttpApiClient);
  });

  it('uses the HTTP client in http mode', () => {
    expect(createApiClient({VITE_API_MODE: 'http'})).toBeInstanceOf(
      HttpApiClient,
    );
  });

  it('uses the mock client in mock mode', () => {
    expect(createApiClient({VITE_API_MODE: 'mock'})).toBeInstanceOf(
      MockApiClient,
    );
  });

  it('uses the mock client under test', () => {
    expect(createApiClient()).toBeInstanceOf(MockApiClient);
  });

  it('rejects an unknown mode', () => {
    expect(() => createApiClient({VITE_API_MODE: 'graphql'})).toThrow(
      /Unknown VITE_API_MODE/,
    );
  });
});

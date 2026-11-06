import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient, ApiError } from '@/api/client';

describe('apiClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('sends X-Unifierr-CSRF: 1 header on non-GET requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ status: 'ok' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await apiClient('/api/setup/folders', {
      method: 'POST',
      body: JSON.stringify({ root: '/srv/unifierr' }),
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, options] = fetchMock.mock.calls[0];
    const headers = options.headers as Headers;
    expect(headers.get('X-Unifierr-CSRF')).toBe('1');
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('does NOT send X-Unifierr-CSRF header on GET requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ status: 'ok' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await apiClient('/api/health', {
      method: 'GET',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, options] = fetchMock.mock.calls[0];
    const headers = options.headers as Headers;
    expect(headers.get('X-Unifierr-CSRF')).toBeNull();
  });

  it('parses {detail: string} error response correctly into ApiError', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'Invalid credentials provided.' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiClient('/api/auth/login', { method: 'POST' })).rejects.toThrow(
      'Invalid credentials provided.'
    );
  });

  it('parses Unifierr {error, explanation, fix} error response correctly', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        error: 'qBittorrent is unreachable',
        explanation: 'The download container did not answer on port 8080.',
        fix: 'Check if qbittorrent container is running and not stuck.',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    try {
      await apiClient('/api/downloads', { method: 'GET' });
      expect.fail('Should have thrown an ApiError');
    } catch (err: unknown) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(502);
      expect(apiErr.message).toBe('qBittorrent is unreachable');
      expect(apiErr.explanation).toBe('The download container did not answer on port 8080.');
      expect(apiErr.fix).toBe('Check if qbittorrent container is running and not stuck.');
    }
  });
});

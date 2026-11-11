import type { UnifierrApiError } from '@/types/api';

export class ApiError extends Error {
  status: number;
  explanation?: string | null;
  fix?: string | null;

  constructor(status: number, message: string, explanation?: string | null, fix?: string | null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.explanation = explanation;
    this.fix = fix;
  }
}

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
  skipAuthRedirect?: boolean;
}

export async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, skipAuthRedirect = false, headers = {}, ...restOptions } = options;

  let url = endpoint;
  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    }
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes('?') ? '&' : '?') + queryString;
    }
  }

  const method = (restOptions.method || 'GET').toUpperCase();
  const reqHeaders = new Headers(headers);

  // Set CSRF token header for all non-GET requests
  if (method !== 'GET') {
    reqHeaders.set('X-Unifierr-CSRF', '1');
  }

  // Set default JSON Content-Type if sending body and not FormData
  if (restOptions.body && !(restOptions.body instanceof FormData)) {
    if (!reqHeaders.has('Content-Type')) {
      reqHeaders.set('Content-Type', 'application/json');
    }
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...restOptions,
      headers: reqHeaders,
      credentials: 'same-origin',
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    // No answer at all (Tailscale or Wi-Fi off, server restarting): say so in plain words.
    throw new ApiError(
      0,
      "Can't reach your Unifierr server right now",
      'This device has no connection to the server at the moment.',
      'Check that Wi-Fi or mobile data is on (and Tailscale, if you use it). It will work again by itself once connected.',
    );
  }

  if (response.status === 401) {
    if (!skipAuthRedirect && !window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/bootstrap')) {
      window.location.href = '/login';
    }
  }

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;
    let explanation: string | null = null;
    let fix: string | null = null;

    try {
      const data: UnifierrApiError = await response.json();
      if (data) {
        if (typeof data.error === 'string') {
          errorMessage = data.error;
        } else if (typeof data.detail === 'string') {
          errorMessage = data.detail;
        } else if (Array.isArray(data.detail)) {
          errorMessage = data.detail.map((d) => d.msg).join(', ');
        } else if (typeof data.message === 'string') {
          errorMessage = data.message;
        }

        explanation = data.explanation || null;
        fix = data.fix || null;
      }
    } catch {
      // response is not JSON
      try {
        const text = await response.text();
        if (text) errorMessage = text;
      } catch {
        // ignore
      }
    }

    throw new ApiError(response.status, errorMessage, explanation, fix);
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }

  return response.blob() as unknown as T;
}

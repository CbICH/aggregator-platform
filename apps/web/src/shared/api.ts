import type { components } from './api.generated';

export type User = components['schemas']['UserResponse'];
export type Role = components['schemas']['Role'];
export type Policy = components['schemas']['RegistrationPolicy'];

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public fields?: Record<string, string>) { super(message); }
}

function csrfToken(): string {
  return document.cookie.split('; ').find((item) => item.startsWith('signal_csrf='))?.split('=')[1] ?? '';
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (options.method && !['GET', 'HEAD'].includes(options.method)) {
    headers.set('X-CSRF-Token', decodeURIComponent(csrfToken()));
  }
  const response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'same-origin' });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, body?.error?.code ?? 'NETWORK_ERROR',
      body?.error?.message ?? 'Не удалось выполнить запрос. Попробуйте снова.', body?.error?.fields);
  }
  return body as T;
}

let csrfToken = null;

async function readResponse(response) {
  if (response.status === 204) return null;
  const type = response.headers.get('content-type') ?? '';
  return type.includes('application/json') ? response.json() : response.text();
}

async function getCsrfToken() {
  if (csrfToken) return csrfToken;
  const response = await fetch('/api/auth/csrf', { credentials: 'same-origin' });
  const data = await readResponse(response);
  if (!response.ok) throw new Error('Impossibile inizializzare la sessione sicura.');
  csrfToken = data.csrfToken;
  return csrfToken;
}

export async function api(path, options = {}) {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers ?? {});
  const isFormData = options.body instanceof FormData;

  if (options.body && !isFormData && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers.set('x-csrf-token', await getCsrfToken());
  }

  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: 'same-origin',
    body: options.body && !isFormData && typeof options.body !== 'string'
      ? JSON.stringify(options.body)
      : options.body
  });
  const data = await readResponse(response);
  if (!response.ok) {
    const error = new Error(data?.error?.message ?? 'Operazione non riuscita.');
    error.status = response.status;
    error.code = data?.error?.code;
    error.details = data?.error?.details;
    throw error;
  }
  if (data?.csrfToken) csrfToken = data.csrfToken;
  return data;
}

export function clearCsrfToken() {
  csrfToken = null;
}

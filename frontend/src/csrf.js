// CSRF helpers for raw fetch() calls.
//
// The backend exposes the session CSRF token via a JS-readable cookie
// (XSRF-TOKEN). State-changing requests must echo it back in the
// X-CSRF-Token header. axios is configured to do this automatically in
// main.jsx; these helpers cover the remaining raw fetch() call sites.

export function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

// Merge the CSRF header into a fetch() options object for non-idempotent
// requests. Always include credentials so the session cookie is sent.
export function withCsrf(options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = { ...(options.headers || {}) };
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    headers['X-CSRF-Token'] = getCsrfToken();
  }
  return { credentials: 'include', ...options, headers };
}

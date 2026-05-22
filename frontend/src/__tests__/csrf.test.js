import { describe, it, expect, beforeEach } from 'vitest';
import { getCsrfToken, withCsrf } from '../csrf.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function setCookie(name, value) {
  Object.defineProperty(document, 'cookie', {
    writable: true,
    value: `${name}=${encodeURIComponent(value)}`,
  });
}

function clearCookie() {
  Object.defineProperty(document, 'cookie', {
    writable: true,
    value: '',
  });
}

// ---------------------------------------------------------------------------
// getCsrfToken
// ---------------------------------------------------------------------------
describe('getCsrfToken', () => {
  beforeEach(() => clearCookie());

  it('returns an empty string when the XSRF-TOKEN cookie is absent', () => {
    expect(getCsrfToken()).toBe('');
  });

  it('returns the decoded token value when the cookie is present', () => {
    setCookie('XSRF-TOKEN', 'my-token-123');
    expect(getCsrfToken()).toBe('my-token-123');
  });

  it('handles URL-encoded characters in the token', () => {
    setCookie('XSRF-TOKEN', 'token with spaces');
    expect(getCsrfToken()).toBe('token with spaces');
  });
});

// ---------------------------------------------------------------------------
// withCsrf
// ---------------------------------------------------------------------------
describe('withCsrf', () => {
  beforeEach(() => clearCookie());

  it('adds credentials: include to every request', () => {
    const result = withCsrf({ method: 'GET' });
    expect(result.credentials).toBe('include');
  });

  it('does NOT add the X-CSRF-Token header for GET requests', () => {
    const result = withCsrf({ method: 'GET' });
    expect(result.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('adds the X-CSRF-Token header for POST requests', () => {
    setCookie('XSRF-TOKEN', 'tok123');
    const result = withCsrf({ method: 'POST' });
    expect(result.headers['X-CSRF-Token']).toBe('tok123');
  });

  it('adds the X-CSRF-Token header for PUT requests', () => {
    setCookie('XSRF-TOKEN', 'tok456');
    const result = withCsrf({ method: 'PUT' });
    expect(result.headers['X-CSRF-Token']).toBe('tok456');
  });

  it('adds the X-CSRF-Token header for DELETE requests', () => {
    setCookie('XSRF-TOKEN', 'tok789');
    const result = withCsrf({ method: 'DELETE' });
    expect(result.headers['X-CSRF-Token']).toBe('tok789');
  });

  it('adds the X-CSRF-Token header for PATCH requests', () => {
    setCookie('XSRF-TOKEN', 'tokABC');
    const result = withCsrf({ method: 'PATCH' });
    expect(result.headers['X-CSRF-Token']).toBe('tokABC');
  });

  it('preserves existing headers when merging', () => {
    setCookie('XSRF-TOKEN', 'tok');
    const result = withCsrf({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    expect(result.headers['Content-Type']).toBe('application/json');
    expect(result.headers['X-CSRF-Token']).toBe('tok');
  });

  it('defaults to GET semantics when method is omitted', () => {
    const result = withCsrf({});
    expect(result.headers['X-CSRF-Token']).toBeUndefined();
  });
});

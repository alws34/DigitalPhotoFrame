// useApiRequest — lightweight hook to handle the "fetch on mount, set state,
// handle error" pattern that appears across multiple pages.
//
// Usage:
//   const { data, loading, error, refetch } = useApiRequest('/api/images');
//
// The hook performs a GET request with credentials on mount (and whenever
// the url changes). A manual refetch() function is exposed for pull-to-refresh
// patterns. 401 responses are treated as unauthenticated — callers receive
// error = 'Unauthorized' and data = null.

import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * @param {string|null} url   Relative API path. Pass null to skip the initial
 *                            fetch (useful for conditional loading).
 * @param {object}      opts  Optional fetch options merged into every request.
 */
export function useApiRequest(url, opts = {}) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(!!url);
  const [error, setError]     = useState(null);

  // Keep a stable reference to opts so the effect dep array stays clean.
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const execute = useCallback(async (signal) => {
    if (!url) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(url, {
        credentials: 'include',
        ...optsRef.current,
        signal,
      });
      if (res.status === 401) {
        setData(null);
        setError('Unauthorized');
        return;
      }
      if (!res.ok) {
        const text = await res.text().catch(() => `HTTP ${res.status}`);
        throw new Error(text || `HTTP ${res.status}`);
      }
      const json = await res.json();
      setData(json);
    } catch (e) {
      if (e.name === 'AbortError') return;
      setError(e.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    if (!url) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    execute(controller.signal);
    return () => controller.abort();
  }, [url, execute]);

  const refetch = useCallback(() => execute(undefined), [execute]);

  return { data, loading, error, refetch };
}

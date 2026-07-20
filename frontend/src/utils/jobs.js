import api from './api';

// Base URL for raw EventSource connections (EventSource can't reuse the axios
// instance / its auth interceptor, so we build the URL and pass the token as a
// query param — the backend's SSE endpoint accepts ?token=).
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/**
 * Track an async processing job to completion.
 *
 * Subscribes to the backend SSE stream for real-time status updates and
 * transparently falls back to polling if SSE is unavailable or the connection
 * drops before the job finishes.
 *
 * @param {string} taskId
 * @param {object} handlers
 * @param {(data:object)=>void} [handlers.onUpdate]   called on every status change
 * @param {(data:object)=>void} [handlers.onComplete] called once when status === 'completed'
 * @param {(err:Error)=>void}   [handlers.onError]    called once on failure/not-found
 * @returns {()=>void} cancel function that stops all tracking
 */
export function trackJob(taskId, { onUpdate, onComplete, onError } = {}) {
  let closed = false;
  let es = null;
  let pollTimer = null;

  const cleanup = () => {
    if (es) { es.close(); es = null; }
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  };

  const finish = (fn, arg) => {
    if (closed) return;
    closed = true;
    cleanup();
    if (fn) fn(arg);
  };

  const handlePayload = (data) => {
    if (closed) return;
    if (data && data.error) {
      finish(onError, new Error(data.error === 'not_found' ? 'Processing job not found.' : data.error));
      return;
    }
    if (onUpdate) onUpdate(data);
    if (data.status === 'completed') {
      finish(onComplete, data);
    } else if (data.status === 'failed') {
      finish(onError, new Error(data.error || 'Processing failed.'));
    }
  };

  const startPolling = () => {
    if (closed || pollTimer) return;
    const poll = async () => {
      if (closed) return;
      try {
        const res = await api.get(`/jobs/${taskId}`);
        handlePayload(res.data);
        if (!closed) pollTimer = setTimeout(poll, 1500);
      } catch (err) {
        finish(onError, err);
      }
    };
    poll();
  };

  // Prefer SSE for true real-time updates; fall back to polling on any failure.
  try {
    const token = localStorage.getItem('token');
    const url = `${API_URL}/jobs/${taskId}/stream?token=${encodeURIComponent(token || '')}`;
    es = new EventSource(url);
    es.onmessage = (e) => {
      try { handlePayload(JSON.parse(e.data)); } catch { /* ignore malformed frame */ }
    };
    es.onerror = () => {
      // EventSource fires 'error' both on transient issues and when the server
      // closes the stream. If we haven't already finished, drop SSE and poll.
      if (!closed) {
        if (es) { es.close(); es = null; }
        startPolling();
      }
    };
  } catch {
    startPolling();
  }

  return () => finish(null, null);
}

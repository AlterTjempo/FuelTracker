// API configuration for frontend
// Uses relative paths so it works on any server
const API_BASE = '/api';

/**
 * Safe fetch wrapper that validates HTTP status and returns parsed JSON.
 * Throws an Error with status info on non-2xx responses.
 *
 * @param {string} url - The URL to fetch
 * @param {object} [options] - Optional fetch options
 * @returns {Promise<any>} Parsed JSON response
 */
export async function safeFetch(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
  }
  return response.json();
}

export default API_BASE;

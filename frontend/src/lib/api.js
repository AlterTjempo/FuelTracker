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

// --- Auth helpers ---

export function getToken() {
  return localStorage.getItem('fuel_token');
}

export function setToken(token) {
  localStorage.setItem('fuel_token', token);
}

export function clearToken() {
  localStorage.removeItem('fuel_token');
  localStorage.removeItem('fuel_user');
}

export function getStoredUser() {
  const raw = localStorage.getItem('fuel_user');
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export function setStoredUser(user) {
  localStorage.setItem('fuel_user', JSON.stringify(user));
}

function authHeaders() {
  const token = getToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function register(username, email, password, captchaToken) {
  return safeFetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password, captcha_token: captchaToken }),
  });
}

export async function login(identifier, password) {
  return safeFetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier, password }),
  });
}

export async function getMe() {
  return safeFetch(`${API_BASE}/auth/me`, {
    headers: authHeaders(),
  });
}

export async function updateProfile({ username, email }) {
  return safeFetch(`${API_BASE}/auth/me/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ username, email }),
  });
}

export async function changePassword(currentPassword, newPassword) {
  return safeFetch(`${API_BASE}/auth/me/password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

// --- Favorites ---

export async function getFavorites() {
  return safeFetch(`${API_BASE}/favorites/`, {
    headers: authHeaders(),
  });
}

export async function addFavorite(stationId) {
  return safeFetch(`${API_BASE}/favorites/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ station_id: stationId }),
  });
}

export async function removeFavorite(stationId) {
  return safeFetch(`${API_BASE}/favorites/${stationId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
}

export default API_BASE;

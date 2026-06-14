import { writable } from 'svelte/store';
import { getStoredUser, getToken, clearToken, setToken, setStoredUser } from './api.js';

function createAuthStore() {
  const storedUser = getToken() ? getStoredUser() : null;
  const { subscribe, set } = writable(storedUser);

  return {
    subscribe,
    login(user, token) {
      setToken(token);
      setStoredUser(user);
      set(user);
    },
    logout() {
      clearToken();
      set(null);
    },
    set,
  };
}

export const currentUser = createAuthStore();

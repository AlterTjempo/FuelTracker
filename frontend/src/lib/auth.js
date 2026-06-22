import { writable } from 'svelte/store';
import { getStoredUser, getToken, clearToken, setToken, setStoredUser } from './api.js';

function createAuthStore() {
  const storedUser = getToken() ? getStoredUser() : null;
  const { subscribe, set, update } = writable(storedUser);

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
    updateUser(user) {
      setStoredUser(user);
      set(user);
    },
    mergeUser(userPatch) {
      let nextUser = null;
      update((current) => {
        nextUser = current ? { ...current, ...userPatch } : userPatch;
        return nextUser;
      });
      if (nextUser) {
        setStoredUser(nextUser);
      }
    },
    set,
  };
}

export const currentUser = createAuthStore();

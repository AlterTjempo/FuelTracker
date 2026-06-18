<script>
  import { currentUser } from '../lib/auth.js';
  import AuthModal from './AuthModal.svelte';
  import SettingsModal from './SettingsModal.svelte';
  import AdminModal from './AdminModal.svelte';

  let showModal = false;
  let showSettings = false;
  let showAdmin = false;
  let showDropdown = false;

  function handleLogout() {
    currentUser.logout();
    showDropdown = false;
  }

  function openSettings() {
    showSettings = true;
    showDropdown = false;
  }

  function openAdmin() {
    showAdmin = true;
    showDropdown = false;
  }

  function toggleDropdown() {
    showDropdown = !showDropdown;
  }

  function closeDropdown(e) {
    if (!e.target.closest('.user-menu')) {
      showDropdown = false;
    }
  }
</script>

<svelte:window on:click={closeDropdown} />

<div class="user-menu">
  {#if $currentUser}
    <button class="user-btn" on:click|stopPropagation={toggleDropdown}>
      <span class="avatar">{$currentUser.username.charAt(0).toUpperCase()}</span>
      <span class="username">{$currentUser.username}</span>
    </button>

    {#if showDropdown}
      <div class="dropdown">
        <div class="dropdown-header">
          <span class="dropdown-name">{$currentUser.username}</span>
          <span class="dropdown-email">{$currentUser.email}</span>
        </div>
        <hr />
        {#if $currentUser.is_admin}
          <button class="dropdown-item admin-item" on:click={openAdmin}>
            Admin Page
          </button>
        {/if}
        <button class="dropdown-item" on:click={openSettings}>
          Settings
        </button>
        <button class="dropdown-item" on:click={handleLogout}>
          Log out
        </button>
      </div>
    {/if}
  {:else}
    <button class="profile-btn" on:click={() => showModal = true} title="Log in">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21c0-4.418 3.582-7 8-7s8 2.582 8 7" />
      </svg>
    </button>
  {/if}
</div>

{#if showModal}
  <AuthModal on:close={() => showModal = false} />
{/if}

{#if showSettings}
  <SettingsModal on:close={() => showSettings = false} />
{/if}

{#if showAdmin}
  <AdminModal on:close={() => showAdmin = false} />
{/if}

<style>
  .user-menu {
    position: relative;
  }

  .profile-btn {
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 50%;
    background: #21262d;
    border: 1px solid #30363d;
    color: #8b949e;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
    transition: border-color 0.2s, color 0.2s;
    min-height: auto;
  }

  .profile-btn:hover {
    border-color: #3b82f6;
    color: #e6edf3;
  }

  .profile-btn svg {
    width: 1.25rem;
    height: 1.25rem;
  }

  .user-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #21262d;
    border: 1px solid #30363d;
    color: #e6edf3;
    padding: 0.375rem 0.75rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.85rem;
    transition: border-color 0.2s;
    min-height: auto;
  }

  .user-btn:hover {
    border-color: #3b82f6;
  }

  .avatar {
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 50%;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.8rem;
    color: white;
  }

  .username {
    max-width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .dropdown {
    position: absolute;
    top: calc(100% + 0.5rem);
    right: 0;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    min-width: 200px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    z-index: 100;
    overflow: hidden;
  }

  .dropdown-header {
    padding: 0.75rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .dropdown-name {
    color: #e6edf3;
    font-weight: 600;
    font-size: 0.9rem;
  }

  .dropdown-email {
    color: #8b949e;
    font-size: 0.8rem;
  }

  hr {
    margin: 0;
    border: none;
    border-top: 1px solid #30363d;
  }

  .dropdown-item {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    color: #e6edf3;
    padding: 0.625rem 1rem;
    cursor: pointer;
    font-size: 0.85rem;
    transition: background 0.15s;
    min-height: auto;
    border-radius: 0;
  }

  .dropdown-item:hover {
    background: #21262d;
  }

  .admin-item {
    color: #c9f7d8;
  }
</style>

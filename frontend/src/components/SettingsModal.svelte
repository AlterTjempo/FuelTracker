<script>
  import { createEventDispatcher } from 'svelte';
  import { updateProfile, changePassword } from '../lib/api.js';
  import { currentUser } from '../lib/auth.js';

  const dispatch = createEventDispatcher();

  let username = $currentUser?.username || '';
  let email = $currentUser?.email || '';
  let profileError = '';
  let profileSuccess = '';
  let profileLoading = false;

  let currentPassword = '';
  let newPassword = '';
  let confirmPassword = '';
  let passwordError = '';
  let passwordSuccess = '';
  let passwordLoading = false;

  // Live password validation for the new password
  $: hasMinLength = newPassword.length >= 8;
  $: hasLowercase = /[a-z]/.test(newPassword);
  $: hasUppercase = /[A-Z]/.test(newPassword);
  $: hasSpecial = /[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;'/`~]/.test(newPassword);
  $: newPasswordValid = hasMinLength && hasLowercase && hasUppercase && hasSpecial;
  $: passwordsMatch = newPassword === confirmPassword;

  function parseError(err) {
    try {
      const parsed = JSON.parse(err.message.replace(/^HTTP \d+: /, ''));
      return parsed.detail || err.message;
    } catch {
      return err.message;
    }
  }

  async function saveProfile() {
    profileError = '';
    profileSuccess = '';
    profileLoading = true;
    try {
      const updated = await updateProfile({ username, email });
      currentUser.updateUser({
        id: updated.id,
        username: updated.username,
        email: updated.email,
        is_admin: updated.is_admin,
      });
      profileSuccess = 'Profile updated';
    } catch (err) {
      profileError = parseError(err);
    } finally {
      profileLoading = false;
    }
  }

  async function savePassword() {
    passwordError = '';
    passwordSuccess = '';
    if (!passwordsMatch) {
      passwordError = 'New passwords do not match';
      return;
    }
    passwordLoading = true;
    try {
      await changePassword(currentPassword, newPassword);
      passwordSuccess = 'Password updated';
      currentPassword = '';
      newPassword = '';
      confirmPassword = '';
    } catch (err) {
      passwordError = parseError(err);
    } finally {
      passwordLoading = false;
    }
  }

  function close() {
    dispatch('close');
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<div class="modal-overlay" on:click={close}>
  <div class="modal" on:click|stopPropagation>
    <button class="close-btn" on:click={close}>&times;</button>

    <h2>Account Settings</h2>

    <section>
      <h3>Profile</h3>
      <div class="field">
        <label for="settings-username">Username</label>
        <input id="settings-username" type="text" bind:value={username} maxlength="50" />
      </div>
      <div class="field">
        <label for="settings-email">Email</label>
        <input id="settings-email" type="email" bind:value={email} />
      </div>

      {#if profileError}
        <div class="error-msg">{profileError}</div>
      {/if}
      {#if profileSuccess}
        <div class="success-msg">{profileSuccess}</div>
      {/if}

      <button class="submit-btn" on:click={saveProfile} disabled={profileLoading}>
        {profileLoading ? 'Saving...' : 'Save Profile'}
      </button>
    </section>

    <hr />

    <section>
      <h3>Change Password</h3>
      <div class="field">
        <label for="current-password">Current Password</label>
        <input id="current-password" type="password" bind:value={currentPassword} placeholder="••••••••" />
      </div>
      <div class="field">
        <label for="new-password">New Password</label>
        <input id="new-password" type="password" bind:value={newPassword} placeholder="••••••••" />
      </div>

      {#if newPassword}
        <div class="password-checks">
          <div class="check" class:valid={hasMinLength}>
            <span class="icon">{hasMinLength ? '✓' : '○'}</span>
            At least 8 characters
          </div>
          <div class="check" class:valid={hasLowercase}>
            <span class="icon">{hasLowercase ? '✓' : '○'}</span>
            Contains a lowercase letter
          </div>
          <div class="check" class:valid={hasUppercase}>
            <span class="icon">{hasUppercase ? '✓' : '○'}</span>
            Contains an uppercase letter
          </div>
          <div class="check" class:valid={hasSpecial}>
            <span class="icon">{hasSpecial ? '✓' : '○'}</span>
            Contains a special character
          </div>
        </div>
      {/if}

      <div class="field">
        <label for="confirm-password">Confirm New Password</label>
        <input id="confirm-password" type="password" bind:value={confirmPassword} placeholder="••••••••" />
        {#if confirmPassword && !passwordsMatch}
          <span class="mismatch">Passwords do not match</span>
        {/if}
      </div>

      {#if passwordError}
        <div class="error-msg">{passwordError}</div>
      {/if}
      {#if passwordSuccess}
        <div class="success-msg">{passwordSuccess}</div>
      {/if}

      <button
        class="submit-btn"
        on:click={savePassword}
        disabled={passwordLoading || !currentPassword || !newPasswordValid || !passwordsMatch}
      >
        {passwordLoading ? 'Updating...' : 'Update Password'}
      </button>
    </section>
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
    overflow-y: auto;
  }

  .modal {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 2rem;
    width: 100%;
    max-width: 420px;
    position: relative;
    margin: auto;
  }

  .close-btn {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: none;
    border: none;
    color: #8b949e;
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0;
    line-height: 1;
    min-height: auto;
  }

  .close-btn:hover {
    color: #e6edf3;
  }

  h2 {
    margin: 0 0 1.5rem 0;
    color: #e6edf3;
    font-size: 1.5rem;
  }

  h3 {
    margin: 0 0 1rem 0;
    color: #c9d1d9;
    font-size: 1rem;
  }

  section {
    margin-bottom: 0.5rem;
  }

  hr {
    margin: 1.5rem 0;
    border: none;
    border-top: 1px solid #30363d;
  }

  .field {
    margin-bottom: 1rem;
  }

  .field label {
    display: block;
    margin-bottom: 0.375rem;
    color: #c9d1d9;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .field input {
    width: 100%;
    padding: 0.625rem 0.75rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.2s;
  }

  .field input:focus {
    border-color: #3b82f6;
  }

  .mismatch {
    display: block;
    margin-top: 0.375rem;
    color: #ff7b72;
    font-size: 0.8rem;
  }

  .password-checks {
    margin-bottom: 1rem;
    padding: 0.75rem;
    background: #0d1117;
    border-radius: 6px;
    border: 1px solid #30363d;
  }

  .check {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0;
    color: #8b949e;
    font-size: 0.825rem;
    transition: color 0.2s;
  }

  .check.valid {
    color: #3fb950;
  }

  .check .icon {
    font-size: 0.9rem;
    width: 1.25rem;
    text-align: center;
  }

  .error-msg {
    background: #3f1f1f;
    color: #ff7b72;
    padding: 0.75rem;
    border-radius: 6px;
    margin-bottom: 1rem;
    font-size: 0.85rem;
    border: 1px solid #5a2828;
  }

  .success-msg {
    background: #16331f;
    color: #3fb950;
    padding: 0.75rem;
    border-radius: 6px;
    margin-bottom: 1rem;
    font-size: 0.85rem;
    border: 1px solid #28502f;
  }

  .submit-btn {
    width: 100%;
    padding: 0.75rem;
    background: #3b82f6;
    border: none;
    border-radius: 6px;
    color: white;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
    min-height: 2.75rem;
  }

  .submit-btn:hover:not(:disabled) {
    background: #2563eb;
  }

  .submit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>

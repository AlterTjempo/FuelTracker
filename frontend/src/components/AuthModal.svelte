<script>
  import { createEventDispatcher, onMount, afterUpdate } from 'svelte';
  import { login, register } from '../lib/api.js';
  import { currentUser } from '../lib/auth.js';

  const dispatch = createEventDispatcher();
  const RECAPTCHA_SITE_KEY = import.meta.env.VITE_RECAPTCHA_SITE_KEY || '';

  let mode = 'login'; // 'login' or 'register'
  let email = '';
  let identifier = '';
  let password = '';
  let username = '';
  let error = '';
  let loading = false;
  let captchaRendered = false;
  let recaptchaPollInterval;
  let recaptchaPollTimeout;

  // Live password validation
  $: hasMinLength = password.length >= 8;
  $: hasLowercase = /[a-z]/.test(password);
  $: hasUppercase = /[A-Z]/.test(password);
  $: hasSpecial = /[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;'/`~]/.test(password);
  $: passwordValid = hasMinLength && hasLowercase && hasUppercase && hasSpecial;

  function loadRecaptchaScript() {
    if (!RECAPTCHA_SITE_KEY) return;
    if (document.getElementById('recaptcha-script')) return;
    const script = document.createElement('script');
    script.id = 'recaptcha-script';
    script.src = 'https://www.google.com/recaptcha/api.js?render=explicit';
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);
  }

  function renderCaptcha() {
    if (!RECAPTCHA_SITE_KEY || mode !== 'register') return;
    if (!window.grecaptcha || !window.grecaptcha.render) return;
    const container = document.getElementById('recaptcha-container');
    if (container && !captchaRendered) {
      container.innerHTML = '';
      window.grecaptcha.render(container, {
        sitekey: RECAPTCHA_SITE_KEY,
        theme: 'dark',
      });
      captchaRendered = true;
    }
  }

  afterUpdate(() => {
    if (mode === 'register' && RECAPTCHA_SITE_KEY) {
      // Attempt to render once script is loaded
      if (window.grecaptcha && window.grecaptcha.render) {
        renderCaptcha();
      }
    } else {
      captchaRendered = false;
    }
  });

  onMount(() => {
    if (RECAPTCHA_SITE_KEY) {
      loadRecaptchaScript();
      // Poll until grecaptcha is available (script loads async)
      recaptchaPollInterval = setInterval(() => {
        if (window.grecaptcha && window.grecaptcha.render) {
          clearInterval(recaptchaPollInterval);
          recaptchaPollInterval = null;
          renderCaptcha();
        }
      }, 200);
      // Clean up after 10s
      recaptchaPollTimeout = setTimeout(() => {
        if (recaptchaPollInterval) {
          clearInterval(recaptchaPollInterval);
          recaptchaPollInterval = null;
        }
      }, 10000);
    }
    return () => {
      if (recaptchaPollInterval) {
        clearInterval(recaptchaPollInterval);
        recaptchaPollInterval = null;
      }
      if (recaptchaPollTimeout) {
        clearTimeout(recaptchaPollTimeout);
        recaptchaPollTimeout = null;
      }
    };
  });

  async function handleSubmit() {
    error = '';
    loading = true;

    try {
      if (mode === 'login') {
        const result = await login(identifier, password);
        currentUser.login(result.user, result.access_token);
      } else {
        // Get captcha token if available and configured
        let captchaToken = null;
        if (RECAPTCHA_SITE_KEY && window.grecaptcha) {
          try {
            captchaToken = window.grecaptcha.getResponse();
          } catch { captchaToken = null; }
          if (!captchaToken) {
            error = 'Please complete the CAPTCHA';
            loading = false;
            return;
          }
        }
        const result = await register(username, email, password, captchaToken);
        currentUser.login(result.user, result.access_token);
      }
      dispatch('close');
    } catch (err) {
      // Parse error message from API
      try {
        const parsed = JSON.parse(err.message.replace(/^HTTP \d+: /, ''));
        error = parsed.detail || err.message;
      } catch {
        error = err.message;
      }
    } finally {
      loading = false;
    }
  }

  function close() {
    dispatch('close');
  }

  function switchMode() {
    mode = mode === 'login' ? 'register' : 'login';
    error = '';
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<div class="modal-overlay" on:click={close}>
  <div class="modal" on:click|stopPropagation>
    <button class="close-btn" on:click={close}>&times;</button>
    
    <h2>{mode === 'login' ? 'Log In' : 'Create Account'}</h2>

    <form on:submit|preventDefault={handleSubmit}>
      {#if mode === 'register'}
        <div class="field">
          <label for="username">Username</label>
          <input 
            id="username" 
            type="text" 
            bind:value={username} 
            placeholder="Your display name"
            required
            maxlength="50"
          />
        </div>

        <div class="field">
          <label for="email">Email</label>
          <input 
            id="email" 
            type="email" 
            bind:value={email} 
            placeholder="you@example.com"
            required
          />
        </div>
      {:else}
        <div class="field">
          <label for="identifier">Email or Username</label>
          <input 
            id="identifier" 
            type="text" 
            bind:value={identifier} 
            placeholder="you@example.com or username"
            required
          />
        </div>
      {/if}

      <div class="field">
        <label for="password">Password</label>
        <input 
          id="password" 
          type="password" 
          bind:value={password} 
          placeholder="••••••••"
          required
        />
      </div>

      {#if mode === 'register'}
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

        {#if RECAPTCHA_SITE_KEY}
          <div id="recaptcha-container"></div>
        {/if}
      {/if}

      {#if error}
        <div class="error-msg">{error}</div>
      {/if}

      <button 
        type="submit" 
        class="submit-btn" 
        disabled={loading || (mode === 'register' && !passwordValid)}
      >
        {#if loading}
          Loading...
        {:else}
          {mode === 'login' ? 'Log In' : 'Create Account'}
        {/if}
      </button>
    </form>

    <div class="switch-mode">
      {#if mode === 'login'}
        Don't have an account? <button class="link-btn" on:click={switchMode}>Sign up</button>
      {:else}
        Already have an account? <button class="link-btn" on:click={switchMode}>Log in</button>
      {/if}
    </div>
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
  }

  .modal {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 2rem;
    width: 100%;
    max-width: 400px;
    position: relative;
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

  .switch-mode {
    text-align: center;
    margin-top: 1.25rem;
    color: #8b949e;
    font-size: 0.85rem;
  }

  .link-btn {
    background: none;
    border: none;
    color: #3b82f6;
    cursor: pointer;
    font-size: 0.85rem;
    padding: 0;
    min-height: auto;
  }

  .link-btn:hover {
    text-decoration: underline;
  }

  #recaptcha-container {
    margin-bottom: 1rem;
  }
</style>

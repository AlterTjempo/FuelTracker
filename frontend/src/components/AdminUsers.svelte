<script>
  import { onMount } from 'svelte'
  import { getAdminUsers } from '../lib/api.js'

  let data = null
  let loading = true
  let error = ''

  onMount(async () => {
    try {
      data = await getAdminUsers()
    } catch (e) {
      try { error = JSON.parse(e.message.replace(/^HTTP \d+: /, '')).detail || e.message } catch { error = e.message }
    } finally {
      loading = false
    }
  })

  const fmtDate = (iso) => new Date(iso).toLocaleDateString('en-GB', { dateStyle: 'medium' })
</script>

{#if loading}
  <div class="card">Loading users…</div>
{:else if error}
  <div class="card err">{error}</div>
{:else if data}
  <div class="grid">
    <div class="card"><span class="muted">Accounts</span><strong>{data.summary.total}</strong><span class="muted small">{data.summary.admins} admin</span></div>
    <div class="card"><span class="muted">New, last 7 days</span><strong>{data.summary.new_7d}</strong><span class="muted small">{data.summary.new_30d} in 30 days</span></div>
    <div class="card"><span class="muted">With favourites</span><strong>{data.summary.with_favorites}</strong><span class="muted small">of {data.summary.total}</span></div>
    <div class="card"><span class="muted">Logged refuels</span><strong>{data.summary.refuels_total}</strong><span class="muted small">{data.summary.with_refuels} users</span></div>
  </div>

  <div class="card">
    <h3>Accounts</h3>
    <div class="table-wrap">
      <table>
        <thead><tr><th>User</th><th>Email</th><th>Joined</th><th>Favourites</th><th>Refuels</th><th>Role</th></tr></thead>
        <tbody>
          {#each data.users as u}
            <tr>
              <td><strong>{u.username}</strong></td>
              <td class="muted">{u.email}</td>
              <td>{fmtDate(u.created_at)}</td>
              <td>{u.favorites}</td>
              <td>{u.refuels}</td>
              <td>{#if u.is_admin}<span class="pill">admin</span>{:else}<span class="muted">user</span>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    {#if data.users.length < data.summary.total}
      <p class="muted small">Showing the newest {data.shown} of {data.summary.total}.</p>
    {/if}
    <p class="note">🔒 {data.note} Emails are masked here.</p>
  </div>
{/if}

<style>
  .card { background: #141d26; border: 1px solid #273341; border-radius: 14px; padding: 1rem; margin-bottom: 1rem; color: #d7e5f3; display: flex; flex-direction: column; gap: 0.2rem; }
  .card.err { color: #ff8b83; border-color: #5b2b2f; background: #27181a; }
  .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.9rem; }
  .grid .card { margin-bottom: 0; }
  .grid strong { font-size: 1.6rem; }
  .grid + .card { margin-top: 1rem; }
  h3 { margin: 0 0 0.5rem; font-size: 1.02rem; }
  .muted { color: #8aa0b6; }
  .small { font-size: 0.78rem; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
  th { text-align: left; color: #8aa0b6; font-weight: 500; padding: 0.4rem 0.6rem; border-bottom: 1px solid #273341; white-space: nowrap; }
  td { padding: 0.5rem 0.6rem; border-bottom: 1px solid #1c2833; white-space: nowrap; }
  .pill { font-size: 0.72rem; padding: 0.1rem 0.5rem; border-radius: 999px; border: 1px solid #4d8ed0; color: #79b8ff; }
  .note { margin: 0.75rem 0 0; font-size: 0.8rem; color: #8aa0b6; }
  @media (min-width: 720px) { .grid { grid-template-columns: repeat(4, 1fr); } }
</style>

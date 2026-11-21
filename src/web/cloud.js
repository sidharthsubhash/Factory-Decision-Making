'use strict';
const byId = id => document.getElementById(id);
async function request(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  };
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(10000)});
  if (!response.ok) throw new Error('Local API returned HTTP ' + response.status);
  return response.json();
}
async function refresh() {
  try {
    const status = await request('/cloud/status');
    byId('status').textContent = status.last_sync_status + ' · ' + status.last_sync_message +
      ' · ' + status.total_synced_packets + ' uploaded';
    byId('send').disabled = !status.enabled;
    byId('disable').disabled = !status.enabled;
  } catch (error) {
    byId('status').textContent = error.message;
  }
}
async function action(operation) {
  try { byId('result').textContent = (await operation()).message; }
  catch (error) { byId('result').textContent = error.message; }
  await refresh();
}
byId('settings').addEventListener('submit', event => {
  event.preventDefault();
  const token = byId('token').value.trim();
  if (!token) return;
  byId('token').value = '';
  action(() => request('/cloud/token', {token, region: byId('region').value}));
});
byId('send').addEventListener('click', () => action(() => request('/cloud/sync', {})));
byId('disable').addEventListener('click', () => action(() => request('/cloud/token', {token:'', region:byId('region').value})));
refresh();
setInterval(refresh, 3000);

'use strict';
const $ = id => document.getElementById(id);
const fields = [
  ['temperature','Temperature','°C'],
  ['vibration','Vibration','g RMS'],
  ['pressure','Pressure','bar'],
  ['current','Current','A'],
  ['speed','Speed','RPM']
];
function showDecision(decision) {
  const status = $('decision-status');
  status.dataset.value = decision.overall_status;
  status.textContent = decision.overall_status.replaceAll('_', ' ');
  const latency = decision.timing?.edge_processing_latency_ms;
  $('decision-latency').textContent = Number.isFinite(latency) ? latency.toFixed(2) + ' ms' : '—';
  const time = new Date(decision.timestamp);
  $('decision-time').textContent = Number.isNaN(time.valueOf()) ? '—' : time.toLocaleTimeString();

  $('decision-readings').replaceChildren(...fields.map(([key, name]) => {
    const reading = decision.readings?.[key];
    const card = document.createElement('div');
    card.className = 'gauge';
    const label = document.createElement('small');
    label.textContent = name;
    const value = document.createElement('strong');
    value.textContent = reading ? new Intl.NumberFormat(undefined, {
      maximumFractionDigits: 3
    }).format(reading.value) + ' ' + reading.unit : '—';
    card.append(label, value);
    return card;
  }));

  const alerts = (decision.worker_recommendations || []).map(alert => {
    const card = document.createElement('article');
    card.dataset.severity = alert.severity;
    const title = document.createElement('h3');
    title.textContent = alert.alert_type.replaceAll('_', ' ');
    const actions = document.createElement('ul');
    for (const recommendation of alert.recommended_worker_actions || []) {
      const item = document.createElement('li');
      item.textContent = recommendation;
      actions.append(item);
    }
    card.append(title, actions);
    return card;
  });
  if (!alerts.length) {
    const empty = document.createElement('p');
    empty.textContent = 'No alerts for this reading.';
    alerts.push(empty);
  }
  $('decision-alerts').replaceChildren(...alerts);
}


const feedId = new URLSearchParams(location.search).get('feed_id');
const feedUrl = feedId ? '/simulator/latest?feed_id=' + encodeURIComponent(feedId) : '/simulator/latest';

async function poll() {
  try {
    const response = await fetch(feedUrl, {
      cache: 'no-store', signal: AbortSignal.timeout(5000)
    });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const decision = await response.json();
    if (decision) {
      showDecision(decision);
      const age = Date.now() - Date.parse(decision.timestamp);
      $('dashboard-feed').textContent = age <= 5000 ? 'Receiving simulator readings' : 'Showing the last recorded decision';
    } else {
      $('dashboard-feed').textContent = 'Waiting for a simulator reading.';
    }
  } catch {
    $('dashboard-feed').textContent = 'Connection lost. Any displayed reading is the last received.';
  } finally {
    setTimeout(poll, 1000);
  }
}
poll();

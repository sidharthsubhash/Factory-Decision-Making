'use strict';
const $ = id => document.getElementById(id);
async function request(url, options) {
  const response = await fetch(url, {...options, signal: AbortSignal.timeout(10000)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'HTTP ' + response.status);
  return data;
}
for (const button of document.querySelectorAll('[data-case]')) {
  button.addEventListener('click', async () => {
    try {
      const d = await request('/demo/model/sample/' + button.dataset.case);
      $('model').textContent = 'Prediction: ' + d.status + ' · anomaly probability ' + (d.anomaly_probability * 100).toFixed(1) + '% · threshold ' + (d.threshold * 100).toFixed(1) + '%\nRecorded label: ' + (d.label ? 'ANOMALY' : 'NORMAL') + ' · SKAB file 11, row index ' + d.row;
    } catch (error) { $('model').textContent = error.message; }
  });
}
$('upload').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    const d = await request('/demo/model/csv', {method:'POST',body:new FormData(event.currentTarget)});
    if (!d.model_version) throw new Error('The API is running an older version. Restart the Factory Edge demo and retry.');
    const c = d.counts;
    const ratio = (a,b) => b ? (100*a/b).toFixed(1) + '%' : 'undefined';
    const metrics = c ? '\nAccuracy ' + ratio(c.tp+c.tn,d.rows) + ' · F1 ' + ratio(2*c.tp,2*c.tp+c.fp+c.fn) + ' · Recall ' + ratio(c.tp,c.tp+c.fn) + ' · False-positive rate ' + ratio(c.fp,c.fp+c.tn) + '\nTP ' + c.tp + ' · TN ' + c.tn + ' · FP ' + c.fp + ' · FN ' + c.fn : '\nAdd an anomaly label column to calculate evaluation metrics.';
    const preview = d.preview.map(r => 'Row ' + r.row + ': ' + (r.anomaly ? 'ANOMALY' : 'NORMAL') + ' (' + (r.score*100).toFixed(1) + '%)').join('\n');
    $('model').textContent = 'Anomaly model v' + d.model_version + '\n' + d.anomalies + ' anomaly predictions across ' + d.rows + ' rows' + metrics + '\n\n' + preview;
  } catch (error) { $('model').textContent = error.message; }
  finally { button.disabled = false; }
});
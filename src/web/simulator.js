'use strict';
const $ = id => document.getElementById(id);
const fields = [
  ['temperature','Temperature','°C'],
  ['vibration','Vibration','g RMS'],
  ['pressure','Pressure','bar'],
  ['current','Current','A'],
  ['speed','Speed','RPM']
];
const presets = [
  ['Normal operation', [78.5,.18,8,18,1450]],
  ['High pressure and vibration', [102.5,.38,11.2,18,1450]],
  ['Critical temperature', [125,.18,8,18,1450]],
  ['Bearing wear', [94,.58,8,24.5,1450]],
  ['Motor overload', [98,.25,7.8,29.5,1390]],
  ['Belt slip', [82,.19,5.8,18,1310]],
  ['Unexpected zero speed', [78.5,.18,8,18,0]],
  ['Commanded stop', [78.5,.18,8,18,0], 'STOP']
];
const feedId = crypto.randomUUID();
$('dashboard-link').href = '/live-dashboard?feed_id=' + encodeURIComponent(feedId);
let streamId = crypto.randomUUID();
let running = true;
let busy = false;
const inputs = fields.map(([key,name,unit],i) => {
  const row = document.createElement('div');
  row.className = 'sensor-control';
  const label = document.createElement('label');
  label.htmlFor = 'reading-' + key;
  label.textContent = name + ' (' + unit + ')';
  const input = document.createElement('input');
  Object.assign(input,{type:'number',id:label.htmlFor,name:key,step:'any',value:presets[0][1][i]});
  row.append(label,input);
  $('controls').append(row);
  return input;
});
let motorCommand = 'RUN';
for (const [name,readings,command = 'RUN'] of presets) {
  const button = document.createElement('button');
  button.textContent = name;
  button.addEventListener('click', () => {
    inputs.forEach((input,index) => { input.value = readings[index]; });
    motorCommand = command;
    streamId = crypto.randomUUID();
    tick();
  });
  $('presets').append(button);
}
async function tick() {
  if (!running || busy) return;
  busy = true;
  const stream = streamId;
  const payload = Object.fromEntries(inputs.map(input => [input.name,input.valueAsNumber]));
  try {
    if (!Object.values(payload).every(Number.isFinite)) {
      $('connection').textContent = 'Enter a finite number for each sensor';
      return;
    }
    const response = await fetch('/simulator/analyse',{
      method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(5000),
      body:JSON.stringify({...payload,run_command:motorCommand,noise:$('noise').checked,stream_id:stream,feed_id:feedId})
    });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    if (stream !== streamId || !running) return;
    $('connection').textContent = running ? 'Streaming five readings to the local API' : 'Streaming paused';
  } catch (error) {
    $('connection').textContent = 'Could not send readings · ' + error.message;
  } finally {
    busy = false;
    if (stream !== streamId) tick();
  }
}
$('run').addEventListener('click', () => {
  running = !running;
  $('run').textContent = running ? 'Pause streaming' : 'Resume streaming';
  $('connection').textContent = running ? 'Connecting…' : 'Streaming paused';
  tick();
});
tick();
setInterval(tick,1000);

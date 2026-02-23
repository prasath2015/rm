const commandInput = document.getElementById('commandInput');
const tokenInput = document.getElementById('tokenInput');
const sendBtn = document.getElementById('sendBtn');
const micBtn = document.getElementById('micBtn');
const stopMicBtn = document.getElementById('stopMicBtn');
const statusText = document.getElementById('statusText');
const logList = document.getElementById('logList');

let recognition;

function setStatus(message) {
  statusText.textContent = message;
}

function getToken() {
  return (tokenInput.value || '').trim();
}

async function apiFetch(url, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) {
    headers['X-Remote-Token'] = token;
  }

  const response = await fetch(url, { ...options, headers });
  const data = await response.json();

  if (!response.ok || !data.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

async function sendCommand(text, source = 'phone') {
  if (!text || !text.trim()) {
    setStatus('Please enter a command first.');
    return;
  }

  setStatus('Sending command...');
  await apiFetch('/api/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, source, token: getToken() }),
  });

  setStatus(`Queued: ${text}`);
}

async function loadLogs() {
  try {
    const data = await apiFetch('/api/logs');
    logList.innerHTML = '';
    data.logs.forEach((item) => {
      const li = document.createElement('li');
      li.className = `status-${item.status}`;
      li.textContent = `[${item.created_at}] ${item.source}: ${item.text} -> ${item.status} (${item.output})`;
      logList.appendChild(li);
    });
  } catch (error) {
    setStatus(error.message);
  }
}

sendBtn.addEventListener('click', async () => {
  try {
    await sendCommand(commandInput.value, 'text');
    commandInput.value = '';
    await loadLogs();
  } catch (error) {
    setStatus(error.message);
  }
});

commandInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    sendBtn.click();
  }
});

function startVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    setStatus('Voice input is not supported on this browser. Use Chrome/Edge on phone.');
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.continuous = true;

  recognition.onstart = () => setStatus('Listening... Speak a command.');
  recognition.onerror = (event) => setStatus(`Voice error: ${event.error}`);
  recognition.onend = () => setStatus('Voice stopped.');

  recognition.onresult = async (event) => {
    const last = event.results[event.results.length - 1];
    const transcript = last[0].transcript.trim();
    commandInput.value = transcript;

    try {
      await sendCommand(transcript, 'voice');
      await loadLogs();
    } catch (error) {
      setStatus(error.message);
    }
  };

  recognition.start();
}

micBtn.addEventListener('click', startVoiceInput);
stopMicBtn.addEventListener('click', () => {
  if (recognition) recognition.stop();
});

tokenInput.addEventListener('change', loadLogs);
setInterval(loadLogs, 2500);
loadLogs();

window.GPT2API = window.GPT2API || {};
window.GPT2API.api = window.GPT2API.api || {};

window.GPT2API.api.API_BASE = window.location.origin;

window.GPT2API.api.getLocalHealth = async function getLocalHealth() {
    const response = await fetch(`${window.GPT2API.api.API_BASE}/healthz`);
    return response.ok;
};

window.GPT2API.api.getQueueStatus = async function getQueueStatus() {
    const response = await fetch(`${window.GPT2API.api.API_BASE}/v1/queue/status`);
    return response.json();
};

window.GPT2API.api.submitLocalImageGeneration = async function submitLocalImageGeneration({ prompt, model, n }) {
    const response = await fetch(`${window.GPT2API.api.API_BASE}/v1/images/generations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, model, n }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Local Gateway HTTP ${response.status}`);
    return data;
};

window.GPT2API.api.getLocalQueueResult = async function getLocalQueueResult(requestId) {
    const response = await fetch(`${window.GPT2API.api.API_BASE}/v1/queue/result/${requestId}`);
    return response.json();
};

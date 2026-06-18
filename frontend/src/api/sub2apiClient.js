window.GPT2API = window.GPT2API || {};
window.GPT2API.api = window.GPT2API.api || {};

window.GPT2API.api.callSub2apiImageGeneration = async function callSub2apiImageGeneration({
    baseUrl,
    token,
    prompt,
    model,
    n,
}) {
    const normalizedBaseUrl = window.GPT2API.api.normalizeBaseUrl(baseUrl);
    if (!normalizedBaseUrl) throw new Error('请输入 Sub2API URL');
    if (!token.trim()) throw new Error('请输入 Sub2API API token');

    const response = await fetch(`${normalizedBaseUrl}/v1/images/generations`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ prompt, model, n }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.detail || data.error?.message || `Sub2API HTTP ${response.status}`);
    }
    return data;
};

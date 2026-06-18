window.GPT2API = window.GPT2API || {};
window.GPT2API.utils = window.GPT2API.utils || {};

window.GPT2API.utils.STORAGE_KEYS = {
    windows: 'gpt2api_conversation_windows',
    activeWindow: 'gpt2api_active_window',
    sourceMode: 'gpt2api_source_mode',
    sub2apiBaseUrl: 'gpt2api_sub2api_base_url',
    rememberToken: 'gpt2api_remember_sub2api_token',
    sub2apiToken: 'gpt2api_sub2api_token',
};

window.GPT2API.utils.MAX_STORED_MESSAGES_PER_WINDOW = 24;

window.GPT2API.utils.safeSetLocalStorage = function safeSetLocalStorage(key, value) {
    try {
        localStorage.setItem(key, value);
        return true;
    } catch (error) {
        if (key === window.GPT2API.utils.STORAGE_KEYS.windows) {
            localStorage.removeItem(window.GPT2API.utils.STORAGE_KEYS.windows);
        }
        console.warn(`Unable to persist ${key}`, error);
        return false;
    }
};

window.GPT2API.utils.serializeWindowsForStorage = function serializeWindowsForStorage(windows) {
    return windows.map((item) => ({
        id: item.id,
        title: item.title,
        createdAt: item.createdAt,
        messages: (item.messages || [])
            .slice(-window.GPT2API.utils.MAX_STORED_MESSAGES_PER_WINDOW)
            .map((message) => ({
                id: message.id,
                role: message.role,
                modality: message.modality,
                source: message.source,
                status: message.status,
                text: message.text,
                prompt: message.prompt,
                createdAt: message.createdAt,
                images: (message.images || []).map((image) => ({
                    id: image.id,
                    revised_prompt: image.revised_prompt,
                    index: image.index,
                    url: image.url && !image.url.startsWith('data:') ? image.url : '',
                    src: '',
                    b64_json: '',
                })),
            })),
    }));
};

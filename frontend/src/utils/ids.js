window.GPT2API = window.GPT2API || {};
window.GPT2API.utils = window.GPT2API.utils || {};

window.GPT2API.utils.makeId = function makeId(prefix) {
    if (window.crypto && window.crypto.randomUUID) {
        return `${prefix}-${window.crypto.randomUUID()}`;
    }
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

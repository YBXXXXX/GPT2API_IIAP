window.GPT2API = window.GPT2API || {};
window.GPT2API.api = window.GPT2API.api || {};

window.GPT2API.api.normalizeBaseUrl = function normalizeBaseUrl(value) {
    return value.trim().replace(/\/+$/, '');
};

window.GPT2API.api.imageUrlFromResult = function imageUrlFromResult(image) {
    if (image.url) return image.url;
    if (image.b64_json) return `data:image/png;base64,${image.b64_json}`;
    return '';
};

window.GPT2API.api.normalizeImageResponse = function normalizeImageResponse(data, prompt) {
    const makeId = window.GPT2API.utils.makeId;
    const images = data?.data || data?.output || [];
    if (!Array.isArray(images)) return [];
    return images
        .map((item, index) => ({
            id: makeId(`image-${index}`),
            src: window.GPT2API.api.imageUrlFromResult(item),
            b64_json: item.b64_json || '',
            url: item.url || '',
            revised_prompt: item.revised_prompt || prompt,
            index,
        }))
        .filter((item) => item.src);
};

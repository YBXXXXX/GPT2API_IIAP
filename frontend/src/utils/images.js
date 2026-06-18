window.GPT2API = window.GPT2API || {};
window.GPT2API.utils = window.GPT2API.utils || {};

window.GPT2API.utils.downloadImage = function downloadImage(image, filename) {
    const link = document.createElement('a');
    link.href = image.src;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
};

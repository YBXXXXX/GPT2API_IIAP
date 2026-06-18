window.GPT2API = window.GPT2API || {};
window.GPT2API.components = window.GPT2API.components || {};

window.GPT2API.components.modalityTabs = [
    { id: 'image', label: 'Image', title: '图像', enabled: true },
    { id: 'video', label: 'Video', title: '视频', enabled: false },
    { id: 'audio', label: 'Audio', title: '音频', enabled: false },
];

window.GPT2API.components.ModalityTabs = function ModalityTabs({
    selectedModality,
    onSelectedModalityChange,
}) {
    return (
        <section className="section">
            <div className="section-title">Modality</div>
            <div className="tabs">
                {window.GPT2API.components.modalityTabs.map((tab) => (
                    <button
                        key={tab.id}
                        className={`tab ${selectedModality === tab.id ? 'active' : ''}`}
                        disabled={!tab.enabled}
                        onClick={() => onSelectedModalityChange(tab.id)}
                        title={tab.enabled ? tab.title : `${tab.title} planned`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>
            <p className="muted" style={{ marginTop: 8 }}>Video / Audio planned; Image is active now.</p>
        </section>
    );
};

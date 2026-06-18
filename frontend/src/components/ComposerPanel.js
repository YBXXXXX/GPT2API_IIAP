window.GPT2API = window.GPT2API || {};
window.GPT2API.components = window.GPT2API.components || {};

window.GPT2API.components.ComposerPanel = function ComposerPanel({
    sourceMode,
    sub2apiBaseUrl,
    sub2apiToken,
    rememberToken,
    selectedModality,
    model,
    n,
    prompt,
    loading,
    jobMessage,
    error,
    onSourceModeChange,
    onSub2apiBaseUrlChange,
    onSub2apiTokenChange,
    onRememberTokenChange,
    onSelectedModalityChange,
    onModelChange,
    onCountChange,
    onPromptChange,
    onGenerate,
}) {
    const SourceSettings = window.GPT2API.components.SourceSettings;
    const ModalityTabs = window.GPT2API.components.ModalityTabs;

    return (
        <aside className="control-panel">
            <SourceSettings
                sourceMode={sourceMode}
                sub2apiBaseUrl={sub2apiBaseUrl}
                sub2apiToken={sub2apiToken}
                rememberToken={rememberToken}
                onSourceModeChange={onSourceModeChange}
                onSub2apiBaseUrlChange={onSub2apiBaseUrlChange}
                onSub2apiTokenChange={onSub2apiTokenChange}
                onRememberTokenChange={onRememberTokenChange}
            />

            <ModalityTabs
                selectedModality={selectedModality}
                onSelectedModalityChange={onSelectedModalityChange}
            />

            <section className="section">
                <div className="section-title">Image Request</div>
                <div className="form-grid">
                    <div className="field">
                        <label>Model</label>
                        <input value={model} onChange={(event) => onModelChange(event.target.value)} />
                    </div>
                    <div className="field">
                        <label>Count</label>
                        <select value={n} onChange={(event) => onCountChange(event.target.value)}>
                            <option value={1}>1</option>
                            <option value={2}>2</option>
                            <option value={3}>3</option>
                            <option value={4}>4</option>
                        </select>
                    </div>
                </div>
                <div className="field">
                    <label>Prompt</label>
                    <textarea
                        value={prompt}
                        onChange={(event) => onPromptChange(event.target.value)}
                        placeholder="描述你想要生成、编辑或分析的多模态任务..."
                    />
                </div>
                <button className="primary" onClick={onGenerate} disabled={loading}>
                    {loading ? 'Running...' : `Run ${selectedModality === 'image' ? 'Image' : selectedModality}`}
                </button>
                {jobMessage && <div className="info" style={{ marginTop: 10 }}>{jobMessage}</div>}
                {error && <div className="error" style={{ marginTop: 10 }}>{error}</div>}
            </section>
        </aside>
    );
};

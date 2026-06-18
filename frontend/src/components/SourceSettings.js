window.GPT2API = window.GPT2API || {};
window.GPT2API.components = window.GPT2API.components || {};

window.GPT2API.components.SourceSettings = function SourceSettings({
    sourceMode,
    sub2apiBaseUrl,
    sub2apiToken,
    rememberToken,
    onSourceModeChange,
    onSub2apiBaseUrlChange,
    onSub2apiTokenChange,
    onRememberTokenChange,
}) {
    return (
        <>
            <section className="section">
                <div className="section-title">Source</div>
                <div className="segmented">
                    <button
                        className={`segment ${sourceMode === 'local' ? 'active' : ''}`}
                        onClick={() => onSourceModeChange('local')}
                    >
                        Local Gateway
                    </button>
                    <button
                        className={`segment ${sourceMode === 'sub2api' ? 'active' : ''}`}
                        onClick={() => onSourceModeChange('sub2api')}
                    >
                        Sub2API
                    </button>
                </div>
            </section>

            {sourceMode === 'sub2api' && (
                <section className="section">
                    <div className="section-title">Sub2API Connection</div>
                    <div className="field">
                        <label>Sub2API URL</label>
                        <input
                            type="text"
                            value={sub2apiBaseUrl}
                            onChange={(event) => onSub2apiBaseUrlChange(event.target.value)}
                            placeholder="http://host:port"
                        />
                    </div>
                    <div className="field">
                        <label>API token</label>
                        <input
                            type="password"
                            value={sub2apiToken}
                            onChange={(event) => onSub2apiTokenChange(event.target.value)}
                            placeholder="sk-..."
                        />
                    </div>
                    <label className="check-row">
                        <input
                            type="checkbox"
                            checked={rememberToken}
                            onChange={(event) => onRememberTokenChange(event.target.checked)}
                        />
                        Remember token
                    </label>
                </section>
            )}
        </>
    );
};

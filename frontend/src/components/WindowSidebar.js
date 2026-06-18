window.GPT2API = window.GPT2API || {};
window.GPT2API.components = window.GPT2API.components || {};

window.GPT2API.components.WindowSidebar = function WindowSidebar({
    apiStatus,
    queueStatus,
    conversationWindows,
    activeWindow,
    loading,
    onAddWindow,
    onSelectWindow,
    onRenameWindow,
    onDeleteWindow,
}) {
    return (
        <aside className="sidebar">
            <div className="brand">
                <h1>GPT2API_IIAP</h1>
                <p>Multimodal invocation console</p>
            </div>

            <div className="status-row">
                <div className={`status-pill ${apiStatus}`}>
                    <span className="dot"></span>
                    {apiStatus === 'online' ? 'Local Gateway online' : 'Local Gateway offline'}
                </div>
                <div className="queue-pill">
                    <span className="dot" style={{ color: '#f4b740' }}></span>
                    Queue {queueStatus.queued || 0} / Running {queueStatus.processing || 0}
                </div>
            </div>

            <button className="new-window" onClick={onAddWindow} disabled={loading}>+ New window</button>

            <div className="window-list">
                {conversationWindows.map((item) => (
                    <div
                        key={item.id}
                        className={`window-item ${item.id === activeWindow?.id ? 'active' : ''}`}
                        onClick={() => onSelectWindow(item.id)}
                    >
                        <div>
                            <input
                                className="window-title"
                                value={item.title}
                                onChange={(event) => onRenameWindow(item.id, event.target.value)}
                                onClick={(event) => event.stopPropagation()}
                                aria-label="Conversation window title"
                            />
                            <div className="window-meta">
                                {item.messages.length} message{item.messages.length === 1 ? '' : 's'}
                            </div>
                        </div>
                        <button
                            className="icon-button"
                            title="Delete window"
                            onClick={(event) => {
                                event.stopPropagation();
                                onDeleteWindow(item.id);
                            }}
                            disabled={conversationWindows.length === 1 || loading}
                        >
                            x
                        </button>
                    </div>
                ))}
            </div>
        </aside>
    );
};

window.GPT2API = window.GPT2API || {};
window.GPT2API.components = window.GPT2API.components || {};

window.GPT2API.components.MessageList = function MessageList({
    activeWindow,
    activeMessages,
    sourceMode,
    loading,
    onClearWindow,
    onDownloadImage,
}) {
    return (
        <main className="workspace">
            <div className="workspace-header">
                <div>
                    <h2>{activeWindow?.title || 'Session'}</h2>
                    <p className="muted">无用户状态；每个窗口仅保存在当前浏览器。</p>
                </div>
                <button className="secondary" onClick={onClearWindow} disabled={!activeMessages.length || loading}>
                    Clear
                </button>
            </div>

            <div className="transcript">
                {!activeMessages.length && (
                    <div className="empty-state">
                        <div>
                            <strong>选择来源，输入 Prompt，然后运行 Image 调用。</strong>
                            <p>Video 和 Audio 入口已预留，后续接入对应 API 时可沿用这个工作台。</p>
                        </div>
                    </div>
                )}

                {activeMessages.map((message) => (
                    <article key={message.id} className={`message ${message.role}`}>
                        <div className="message-head">
                            <span>
                                {message.role === 'user' ? 'User' : 'Assistant'} · {message.modality || 'image'} · {message.source || sourceMode}
                            </span>
                            <span>{new Date(message.createdAt).toLocaleTimeString()}</span>
                        </div>
                        <div className="message-text">{message.text}</div>
                        {message.images?.length > 0 && (
                            <div className="image-grid">
                                {message.images.map((image) => (
                                    <div key={image.id} className="image-result">
                                        <img src={image.src} alt={image.revised_prompt || 'Generated image'} />
                                        <div className="image-actions">
                                            <button
                                                className="secondary"
                                                onClick={() => onDownloadImage(image, `generated_${image.index + 1}.png`)}
                                            >
                                                Download
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </article>
                ))}
            </div>
        </main>
    );
};

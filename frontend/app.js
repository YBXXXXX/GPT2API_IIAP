const { useState, useEffect, useCallback, useRef } = React;

const API_BASE = window.location.origin;

function App() {
    const [prompt, setPrompt] = useState('');
    const [model, setModel] = useState('gpt-image-1');
    const [n, setN] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [results, setResults] = useState([]);
    const [apiStatus, setApiStatus] = useState('checking');
    const [queueStatus, setQueueStatus] = useState({ queued: 0, processing: 0 });
    const [pollRequestId, setPollRequestId] = useState(null);
    const [queuePosition, setQueuePosition] = useState(-1);
    const pollRef = useRef(null);

    // Load API status and queue status
    useEffect(() => {
        fetch(`${API_BASE}/healthz`)
            .then(r => r.ok ? setApiStatus('online') : setApiStatus('offline'))
            .catch(() => setApiStatus('offline'));

        const interval = setInterval(() => {
            fetch(`${API_BASE}/v1/queue/status`)
                .then(r => r.json())
                .then(data => setQueueStatus(data))
                .catch(() => {});
        }, 2000);
        return () => clearInterval(interval);
    }, []);

    // Poll for result
    useEffect(() => {
        if (!pollRequestId) return;

        pollRef.current = setInterval(async () => {
            try {
                const resp = await fetch(`${API_BASE}/v1/queue/result/${pollRequestId}`);
                const data = await resp.json();
                if (data.status === 'done') {
                    clearInterval(pollRef.current);
                    setLoading(false);
                    setQueuePosition(-1);
                    const images = data.data?.data || [];
                    setResults(images.map((img, idx) => ({
                        id: `${Date.now()}-${idx}`,
                        b64_json: img.b64_json,
                        revised_prompt: img.revised_prompt || prompt,
                        index: idx,
                    })));
                } else if (data.status === 'error') {
                    clearInterval(pollRef.current);
                    setLoading(false);
                    setQueuePosition(-1);
                    setError(data.detail || '生成失败');
                } else {
                    setQueuePosition(data.position >= 0 ? data.position : 0);
                }
            } catch (err) {
                setError(err.message);
                clearInterval(pollRef.current);
                setLoading(false);
            }
        }, 1500);

        return () => clearInterval(pollRef.current);
    }, [pollRequestId]);

    const handleGenerate = useCallback(async () => {
        if (!prompt.trim()) {
            setError('请输入 Prompt');
            return;
        }

        setLoading(true);
        setError('');
        setResults([]);
        setQueuePosition(-1);

        try {
            const resp = await fetch(`${API_BASE}/v1/images/generations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ prompt, model, n: parseInt(n) }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.detail || `HTTP ${resp.status}`);
            }
            setPollRequestId(data.request_id);
        } catch (err) {
            setError(err.message || '提交失败');
            setLoading(false);
        }
    }, [prompt, model, n, apiKey]);

    const clearResults = () => {
        setResults([]);
        setError('');
        setPollRequestId(null);
        setQueuePosition(-1);
    };

    const downloadImage = (b64, filename) => {
        const link = document.createElement('a');
        link.href = `data:image/png;base64,${b64}`;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div className="container">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <div>
                    <h1>GPT2API_IIAP</h1>
                    <p className="subtitle">ChatGPT Web 图像生成网关</p>
                </div>
                <div className={`api-status ${apiStatus}`}>
                    <span className="dot"></span>
                    {apiStatus === 'online' ? '服务在线' : '服务离线'}
                </div>
            </div>

            <div className="card">
                <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
                    <div className="queue-badge">
                        <span className="dot" style={{ background: '#f59e0b' }}></span>
                        排队中: {queueStatus.queued}
                    </div>
                    <div className="queue-badge">
                        <span className="dot" style={{ background: '#3b82f6' }}></span>
                        生成中: {queueStatus.processing}
                    </div>
                </div>

                <div className="form-group">
                    <label>Prompt</label>
                    <textarea
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        placeholder="描述你想要生成的图片..."
                    />
                </div>

                <div className="row">
                    <div className="form-group">
                        <label>Model</label>
                        <select value={model} onChange={(e) => setModel(e.target.value)}>
                            <option value="gpt-image-1">gpt-image-1</option>
                            <option value="gpt-image-2">gpt-image-2</option>
                            <option value="auto">auto</option>
                        </select>
                    </div>
                    <div className="form-group">
                        <label>数量 (n)</label>
                        <select value={n} onChange={(e) => setN(e.target.value)}>
                            <option value={1}>1</option>
                            <option value={2}>2</option>
                            <option value={3}>3</option>
                            <option value={4}>4</option>
                        </select>
                    </div>
                </div>

                <div style={{ display: 'flex', gap: 12, marginTop: 8, alignItems: 'center' }}>
                    <button
                        className="btn btn-primary"
                        onClick={handleGenerate}
                        disabled={loading}
                    >
                        {loading && <span className="spinner"></span>}
                        {loading ? '生成中...' : '生成图片'}
                    </button>
                    {results.length > 0 && (
                        <button
                            className="btn"
                            onClick={clearResults}
                            style={{ background: '#2a2a2a', color: '#ccc' }}
                        >
                            清除结果
                        </button>
                    )}
                </div>

                {loading && queuePosition >= 0 && (
                    <div className="info" style={{ marginTop: 12 }}>
                        当前排队位置: #{queuePosition + 1}
                    </div>
                )}

                {error && <div className="error">{error}</div>}
            </div>

            {loading && results.length === 0 && !error && (
                <div className="card loading-overlay">
                    <div className="spinner"></div>
                    <p style={{ color: '#888' }}>
                        {queuePosition >= 0 ? `排队中 (#${queuePosition + 1})...` : '正在生成图片，请稍候...'}
                    </p>
                </div>
            )}

            {results.length > 0 && (
                <div className="card">
                    <h3 style={{ marginBottom: 16, fontSize: '1.1rem' }}>生成结果</h3>
                    <div className="results">
                        {results.map((img) => (
                            <div key={img.id} className="image-card">
                                <img
                                    src={`data:image/png;base64,${img.b64_json}`}
                                    alt={`Generated ${img.index + 1}`}
                                />
                                <div className="image-info">
                                    {img.revised_prompt}
                                </div>
                                <button
                                    className="btn btn-primary"
                                    style={{ margin: '12px 16px', padding: '8px 16px', fontSize: '0.85rem' }}
                                    onClick={() => downloadImage(img.b64_json, `generated_${img.index + 1}.png`)}
                                >
                                    下载图片
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);

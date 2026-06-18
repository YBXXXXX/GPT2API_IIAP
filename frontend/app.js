const { useState, useEffect, useCallback, useRef } = React;

const API_BASE = window.location.origin;

function App() {
    const [prompt, setPrompt] = useState('');
    const [n, setN] = useState(1);
    const [loading, setLoading] = useState(false);
    const [jobStatus, setJobStatus] = useState('idle');
    const [completedCount, setCompletedCount] = useState(0);
    const [requestedCount, setRequestedCount] = useState(1);
    const [jobMessage, setJobMessage] = useState('');
    const [error, setError] = useState('');
    const [results, setResults] = useState([]);
    const [apiStatus, setApiStatus] = useState('checking');
    const [queueStatus, setQueueStatus] = useState({ queued: 0, processing: 0 });
    const [pollRequestId, setPollRequestId] = useState(null);
    const [queuePosition, setQueuePosition] = useState(-1);
    const pollRef = useRef(null);

    const applyQueuePayload = useCallback((data) => {
        if (data.status === 'done') {
            setLoading(false);
            setJobStatus('idle');
            setCompletedCount(data.completed || data.data?.data?.length || 0);
            setRequestedCount(data.requested_n || n);
            setJobMessage('');
            setQueuePosition(-1);
            const images = data.data?.data || [];
            setResults(images.map((img, idx) => ({
                id: `${idx}-${img.b64_json.slice(0, 16)}`,
                b64_json: img.b64_json,
                revised_prompt: img.revised_prompt || prompt,
                index: idx,
            })));
            sessionStorage.removeItem('gpt2api_active_request');
            return 'done';
        }

        if (data.status === 'error') {
            setLoading(false);
            setJobStatus('idle');
            setCompletedCount(0);
            setJobMessage('');
            setQueuePosition(-1);
            setError(data.detail || '生成失败');
            sessionStorage.removeItem('gpt2api_active_request');
            return 'error';
        }

        if (data.status === 'processing') {
            setJobStatus('processing');
            setCompletedCount(data.completed || 0);
            setRequestedCount(data.requested_n || n);
            setJobMessage(data.message || '正在生成图片');
            setQueuePosition(-1);
            const images = data.data?.data || [];
            if (images.length > 0) {
                setResults(images.map((img, idx) => ({
                    id: `${idx}-${img.b64_json.slice(0, 16)}`,
                    b64_json: img.b64_json,
                    revised_prompt: img.revised_prompt || prompt,
                    index: idx,
                })));
            }
            return 'processing';
        }

        if (data.status === 'queued') {
            setJobStatus('queued');
            setCompletedCount(0);
            setRequestedCount(n);
            setJobMessage('');
            setQueuePosition(data.position >= 0 ? data.position : 0);
            return 'queued';
        }

        if (data.status === 'not_found') {
            setLoading(false);
            setJobStatus('idle');
            setCompletedCount(0);
            setJobMessage('');
            setError('任务不存在或已过期');
            sessionStorage.removeItem('gpt2api_active_request');
            return 'not_found';
        }

        return 'unknown';
    }, [n, prompt]);

    const pollOnce = useCallback(async (requestId) => {
        const resp = await fetch(`${API_BASE}/v1/queue/result/${requestId}`);
        const data = await resp.json();
        return applyQueuePayload(data);
    }, [applyQueuePayload]);

    // Load API status and queue status
    useEffect(() => {
        fetch(`${API_BASE}/healthz`)
            .then(r => r.ok ? setApiStatus('online') : setApiStatus('offline'))
            .catch(() => setApiStatus('offline'));

        const activeRequestId = sessionStorage.getItem('gpt2api_active_request');
        if (activeRequestId) {
            setLoading(true);
            setPollRequestId(activeRequestId);
        }

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

        pollOnce(pollRequestId).then((state) => {
            if (state === 'done' || state === 'error' || state === 'not_found') {
                if (pollRef.current) {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                }
            }
        }).catch((err) => {
            setError(err.message);
            setLoading(false);
            setJobStatus('idle');
        });

        pollRef.current = setInterval(async () => {
            try {
                const state = await pollOnce(pollRequestId);
                if (state === 'done' || state === 'error' || state === 'not_found') {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                }
            } catch (err) {
                setError(err.message);
                clearInterval(pollRef.current);
                pollRef.current = null;
                setLoading(false);
                setJobStatus('idle');
                setCompletedCount(0);
                setJobMessage('');
            }
        }, 1500);

        return () => clearInterval(pollRef.current);
    }, [pollRequestId]);

    const handleGenerate = useCallback(async () => {
        if (!prompt.trim()) {
            setError('请输入 Prompt');
            return;
        }

        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }

        setLoading(true);
        setJobStatus('queued');
        setCompletedCount(0);
        setRequestedCount(parseInt(n));
        setJobMessage('');
        setError('');
        setResults([]);
        setPollRequestId(null);
        setQueuePosition(-1);

        try {
            const resp = await fetch(`${API_BASE}/v1/images/generations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ prompt, model: 'gpt-image-2', n: parseInt(n) }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.detail || `HTTP ${resp.status}`);
            }
            sessionStorage.setItem('gpt2api_active_request', data.request_id);
            setPollRequestId(data.request_id);
        } catch (err) {
            setError(err.message || '提交失败');
            setLoading(false);
        }
    }, [prompt, n]);

    const clearResults = () => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
        setResults([]);
        setError('');
        setJobStatus('idle');
        setCompletedCount(0);
        setJobMessage('');
        sessionStorage.removeItem('gpt2api_active_request');
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
                        <input type="text" value="gpt-image-2" readOnly />
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

                {loading && jobStatus === 'queued' && queuePosition >= 0 && (
                    <div className="info" style={{ marginTop: 12 }}>
                        当前排队位置: #{queuePosition + 1}
                    </div>
                )}

                {loading && jobStatus === 'processing' && (
                    <div className="info" style={{ marginTop: 12 }}>
                        {jobMessage || `正在生成第 ${Math.min(requestedCount, completedCount + 1)} 张，共 ${requestedCount} 张`}
                    </div>
                )}

                {error && <div className="error">{error}</div>}
            </div>

            {loading && results.length === 0 && !error && (
                <div className="card loading-overlay">
                    <div className="spinner"></div>
                    <p style={{ color: '#888' }}>
                        {jobStatus === 'queued'
                            ? `排队中 (#${queuePosition + 1})...`
                            : (jobMessage || `正在生成第 ${Math.min(requestedCount, completedCount + 1)} 张，共 ${requestedCount} 张...`)}
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

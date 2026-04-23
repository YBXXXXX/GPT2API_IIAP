const { useState, useEffect, useCallback } = React;

const API_BASE = window.location.origin;

function App() {
    const [adminToken, setAdminToken] = useState(localStorage.getItem('gpt2api_admin_token') || '');
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [checking, setChecking] = useState(true);
    const [activeTab, setActiveTab] = useState('accounts');
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [importJson, setImportJson] = useState('');

    // Check login on mount
    useEffect(() => {
        const token = localStorage.getItem('gpt2api_admin_token');
        if (token) {
            verifyToken(token);
        } else {
            setChecking(false);
        }
    }, []);

    const verifyToken = async (token) => {
        try {
            const resp = await fetch(`${API_BASE}/admin/status`, {
                headers: { 'authorization': `Bearer ${token}` }
            });
            if (resp.ok) {
                setIsLoggedIn(true);
                setAdminToken(token);
            } else {
                localStorage.removeItem('gpt2api_admin_token');
            }
        } catch (e) {
            localStorage.removeItem('gpt2api_admin_token');
        }
        setChecking(false);
    };

    const handleLogin = async () => {
        setError('');
        if (!adminToken.trim()) {
            setError('请输入 Admin Token');
            return;
        }
        setLoading(true);
        try {
            const resp = await fetch(`${API_BASE}/admin/status`, {
                headers: { 'authorization': `Bearer ${adminToken.trim()}` }
            });
            if (resp.ok) {
                localStorage.setItem('gpt2api_admin_token', adminToken.trim());
                setIsLoggedIn(true);
            } else {
                setError('Admin Token 无效');
            }
        } catch (e) {
            setError('连接失败');
        }
        setLoading(false);
    };

    const handleLogout = () => {
        localStorage.removeItem('gpt2api_admin_token');
        setIsLoggedIn(false);
        setAdminToken('');
    };

    const fetchAccounts = useCallback(async () => {
        setLoading(true);
        try {
            const resp = await fetch(`${API_BASE}/admin/accounts`, {
                headers: { 'authorization': `Bearer ${adminToken}` }
            });
            if (resp.ok) {
                const data = await resp.json();
                setAccounts(data);
            } else if (resp.status === 401) {
                handleLogout();
            }
        } catch (e) {
            setError('获取账号列表失败');
        }
        setLoading(false);
    }, [adminToken]);

    useEffect(() => {
        if (isLoggedIn && activeTab === 'accounts') {
            fetchAccounts();
        }
    }, [isLoggedIn, activeTab, fetchAccounts]);

    const handleImport = async () => {
        setError('');
        setSuccess('');
        if (!importJson.trim()) {
            setError('请输入 sub2api JSON');
            return;
        }
        setLoading(true);
        try {
            const resp = await fetch(`${API_BASE}/admin/accounts/import-sub2api`, {
                method: 'POST',
                headers: {
                    'content-type': 'application/json',
                    'authorization': `Bearer ${adminToken}`
                },
                body: JSON.stringify({
                    accounts_json: importJson.trim(),
                    auto_refresh_metadata: true
                })
            });
            const data = await resp.json();
            if (resp.ok) {
                setSuccess(`成功导入 ${data.imported_count} 个账号`);
                setImportJson('');
                fetchAccounts();
            } else {
                setError(data.detail || '导入失败');
            }
        } catch (e) {
            setError('导入请求失败');
        }
        setLoading(false);
    };

    const handleRefresh = async (accessToken) => {
        setError('');
        setSuccess('');
        setLoading(true);
        try {
            const resp = await fetch(`${API_BASE}/admin/accounts/refresh`, {
                method: 'POST',
                headers: {
                    'content-type': 'application/json',
                    'authorization': `Bearer ${adminToken}`
                },
                body: JSON.stringify({ access_tokens: [accessToken] })
            });
            if (resp.ok) {
                setSuccess('刷新成功');
                fetchAccounts();
            } else {
                const data = await resp.json();
                setError(data.detail || '刷新失败');
            }
        } catch (e) {
            setError('刷新请求失败');
        }
        setLoading(false);
    };

    const handleDelete = async (accessToken) => {
        if (!confirm('确定要删除这个账号吗？')) return;
        setError('');
        setSuccess('');
        setLoading(true);
        try {
            const resp = await fetch(`${API_BASE}/admin/accounts`, {
                method: 'DELETE',
                headers: {
                    'content-type': 'application/json',
                    'authorization': `Bearer ${adminToken}`
                },
                body: JSON.stringify({ access_tokens: [accessToken] })
            });
            if (resp.ok) {
                setSuccess('删除成功');
                fetchAccounts();
            } else {
                const data = await resp.json();
                setError(data.detail || '删除失败');
            }
        } catch (e) {
            setError('删除请求失败');
        }
        setLoading(false);
    };

    if (checking) {
        return (
            <div className="container">
                <div className="card loading-overlay" style={{ textAlign: 'center', padding: 60 }}>
                    <div className="spinner"></div>
                    <p style={{ color: '#888', marginTop: 16 }}>验证中...</p>
                </div>
            </div>
        );
    }

    if (!isLoggedIn) {
        return (
            <div className="container">
                <div style={{ maxWidth: 400, margin: '0 auto', paddingTop: 80 }}>
                    <h1 style={{ textAlign: 'center' }}>管理面板</h1>
                    <p className="subtitle" style={{ textAlign: 'center' }}>GPT2API_IIAP Admin</p>
                    <div className="card">
                        <div className="form-group">
                            <label>Admin Token</label>
                            <input
                                type="password"
                                value={adminToken}
                                onChange={(e) => setAdminToken(e.target.value)}
                                placeholder="输入管理员密码..."
                                onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                            />
                        </div>
                        <button
                            className="btn btn-primary"
                            onClick={handleLogin}
                            disabled={loading}
                            style={{ width: '100%' }}
                        >
                            {loading && <span className="spinner"></span>}
                            {loading ? '验证中...' : '登录'}
                        </button>
                        {error && <div className="error">{error}</div>}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="container">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <div>
                    <h1>管理面板</h1>
                    <p className="subtitle">GPT2API_IIAP 账号与配置管理</p>
                </div>
                <button className="btn btn-secondary" onClick={handleLogout}>
                    退出登录
                </button>
            </div>

            <div className="nav">
                <a className={activeTab === 'accounts' ? 'active' : ''} onClick={() => { setActiveTab('accounts'); setError(''); setSuccess(''); }}>
                    账号列表
                </a>
                <a className={activeTab === 'import' ? 'active' : ''} onClick={() => { setActiveTab('import'); setError(''); setSuccess(''); }}>
                    导入账号
                </a>
            </div>

            {error && <div className="error">{error}</div>}
            {success && <div className="success">{success}</div>}

            <div className={`section ${activeTab === 'accounts' ? 'active' : ''}`}>
                <div className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                        <h3>账号列表 ({accounts.length})</h3>
                        <button className="btn btn-secondary" onClick={fetchAccounts} disabled={loading}>
                            {loading ? <span className="spinner"></span> : '刷新'}
                        </button>
                    </div>
                    {accounts.length === 0 ? (
                        <p style={{ color: '#888', textAlign: 'center', padding: 40 }}>暂无账号，请先导入</p>
                    ) : (
                        <table className="account-table">
                            <thead>
                                <tr>
                                    <th>名称</th>
                                    <th>邮箱</th>
                                    <th>状态</th>
                                    <th>额度</th>
                                    <th>Token</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                {accounts.map((acc) => (
                                    <tr key={acc.name}>
                                        <td>{acc.name}</td>
                                        <td>{acc.email || '-'}</td>
                                        <td>
                                            <span className={`status-badge status-${acc.status}`}>
                                                {acc.status}
                                            </span>
                                        </td>
                                        <td>{acc.quota_known ? acc.quota_remaining : '未知'}</td>
                                        <td className="token-mask">
                                            {acc.access_token?.slice(0, 20)}...
                                            {acc.refresh_token ? ' (有refresh)' : ''}
                                        </td>
                                        <td>
                                            <div className="actions">
                                                <button
                                                    className="btn btn-secondary"
                                                    onClick={() => handleRefresh(acc.access_token)}
                                                    disabled={loading}
                                                >
                                                    刷新
                                                </button>
                                                <button
                                                    className="btn btn-danger"
                                                    onClick={() => handleDelete(acc.access_token)}
                                                    disabled={loading}
                                                >
                                                    删除
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            <div className={`section ${activeTab === 'import' ? 'active' : ''}`}>
                <div className="card">
                    <h3 style={{ marginBottom: 16 }}>导入 sub2api 账号</h3>
                    <p style={{ color: '#888', marginBottom: 16, fontSize: '0.9rem' }}>
                        粘贴 sub2api 导出的 JSON 内容（包含 accounts 数组）
                    </p>
                    <div className="form-group">
                        <textarea
                            value={importJson}
                            onChange={(e) => setImportJson(e.target.value)}
                            placeholder={'{\n  "accounts": [\n    {\n      "name": "...",\n      "credentials": {\n        "access_token": "...",\n        "refresh_token": "..."\n      }\n    }\n  ]\n}'}
                        />
                    </div>
                    <button
                        className="btn btn-primary"
                        onClick={handleImport}
                        disabled={loading}
                    >
                        {loading && <span className="spinner"></span>}
                        {loading ? '导入中...' : '导入'}
                    </button>
                </div>
            </div>
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);

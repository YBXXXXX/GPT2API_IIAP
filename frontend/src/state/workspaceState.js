window.GPT2API = window.GPT2API || {};
window.GPT2API.state = window.GPT2API.state || {};

window.GPT2API.state.createWindow = function createWindow(title = 'Image Workspace') {
    return {
        id: window.GPT2API.utils.makeId('window'),
        title,
        createdAt: new Date().toISOString(),
        messages: [],
    };
};

window.GPT2API.state.loadWindows = function loadWindows() {
    const { STORAGE_KEYS, serializeWindowsForStorage } = window.GPT2API.utils;
    try {
        const parsed = JSON.parse(localStorage.getItem(STORAGE_KEYS.windows) || '[]');
        if (Array.isArray(parsed) && parsed.length > 0) return serializeWindowsForStorage(parsed);
    } catch (_) {
        localStorage.removeItem(STORAGE_KEYS.windows);
    }
    return [window.GPT2API.state.createWindow()];
};

window.GPT2API.state.useWorkspaceState = function useWorkspaceState() {
    const { useCallback, useEffect, useMemo, useRef, useState } = React;
    const { STORAGE_KEYS, safeSetLocalStorage, serializeWindowsForStorage } = window.GPT2API.utils;
    const createWindow = window.GPT2API.state.createWindow;
    const [conversationWindows, setConversationWindows] = useState(window.GPT2API.state.loadWindows);
    const [activeWindowId, setActiveWindowId] = useState(localStorage.getItem(STORAGE_KEYS.activeWindow) || '');
    const [sourceMode, setSourceMode] = useState(localStorage.getItem(STORAGE_KEYS.sourceMode) || 'local');
    const [selectedModality, setSelectedModality] = useState('image');
    const [sub2apiBaseUrl, setSub2apiBaseUrl] = useState(localStorage.getItem(STORAGE_KEYS.sub2apiBaseUrl) || '');
    const [rememberToken, setRememberToken] = useState(localStorage.getItem(STORAGE_KEYS.rememberToken) === 'true');
    const [sub2apiToken, setSub2apiToken] = useState(
        localStorage.getItem(STORAGE_KEYS.rememberToken) === 'true'
            ? (localStorage.getItem(STORAGE_KEYS.sub2apiToken) || '')
            : ''
    );
    const [model, setModel] = useState('gpt-image-2');
    const [n, setN] = useState(1);
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [jobMessage, setJobMessage] = useState('');
    const [apiStatus, setApiStatus] = useState('checking');
    const [queueStatus, setQueueStatus] = useState({ queued: 0, processing: 0 });
    const pollRef = useRef(null);

    const activeWindow = useMemo(
        () => conversationWindows.find((item) => item.id === activeWindowId) || conversationWindows[0],
        [conversationWindows, activeWindowId]
    );

    useEffect(() => {
        if (!conversationWindows.some((item) => item.id === activeWindowId) && conversationWindows[0]) {
            setActiveWindowId(conversationWindows[0].id);
        }
    }, [conversationWindows, activeWindowId]);

    useEffect(() => {
        safeSetLocalStorage(
            STORAGE_KEYS.windows,
            JSON.stringify(serializeWindowsForStorage(conversationWindows))
        );
    }, [STORAGE_KEYS.windows, conversationWindows, safeSetLocalStorage, serializeWindowsForStorage]);

    useEffect(() => {
        if (activeWindow?.id) safeSetLocalStorage(STORAGE_KEYS.activeWindow, activeWindow.id);
    }, [STORAGE_KEYS.activeWindow, activeWindow?.id, safeSetLocalStorage]);

    useEffect(() => {
        safeSetLocalStorage(STORAGE_KEYS.sourceMode, sourceMode);
    }, [STORAGE_KEYS.sourceMode, safeSetLocalStorage, sourceMode]);

    useEffect(() => {
        safeSetLocalStorage(STORAGE_KEYS.sub2apiBaseUrl, sub2apiBaseUrl);
    }, [STORAGE_KEYS.sub2apiBaseUrl, safeSetLocalStorage, sub2apiBaseUrl]);

    useEffect(() => {
        safeSetLocalStorage(STORAGE_KEYS.rememberToken, String(rememberToken));
        if (rememberToken) {
            safeSetLocalStorage(STORAGE_KEYS.sub2apiToken, sub2apiToken);
        } else {
            localStorage.removeItem(STORAGE_KEYS.sub2apiToken);
        }
    }, [STORAGE_KEYS.rememberToken, STORAGE_KEYS.sub2apiToken, rememberToken, safeSetLocalStorage, sub2apiToken]);

    const updateActiveWindow = useCallback((updater) => {
        setConversationWindows((windows) => windows.map((item) => {
            if (item.id !== activeWindow?.id) return item;
            return updater(item);
        }));
    }, [activeWindow?.id]);

    const updateMessage = useCallback((messageId, patch) => {
        updateActiveWindow((item) => ({
            ...item,
            messages: item.messages.map((message) => (
                message.id === messageId ? { ...message, ...patch } : message
            )),
        }));
    }, [updateActiveWindow]);

    const addWindow = useCallback(() => {
        const next = createWindow(`Session ${conversationWindows.length + 1}`);
        setConversationWindows((windows) => [next, ...windows]);
        setActiveWindowId(next.id);
        setError('');
        setJobMessage('');
    }, [conversationWindows.length, createWindow]);

    const deleteWindow = useCallback((id) => {
        setConversationWindows((windows) => {
            if (windows.length === 1) return windows;
            const remaining = windows.filter((item) => item.id !== id);
            if (id === activeWindow?.id) setActiveWindowId(remaining[0].id);
            return remaining;
        });
    }, [activeWindow?.id]);

    const renameWindow = useCallback((id, title) => {
        setConversationWindows((windows) => windows.map((item) => (
            item.id === id ? { ...item, title } : item
        )));
    }, []);

    const clearWindow = useCallback(() => {
        updateActiveWindow((item) => ({ ...item, messages: [] }));
        setError('');
        setJobMessage('');
    }, [updateActiveWindow]);

    const appendPair = useCallback((promptText) => {
        const userMessage = {
            id: window.GPT2API.utils.makeId('message'),
            role: 'user',
            modality: selectedModality,
            source: sourceMode,
            text: promptText,
            createdAt: new Date().toISOString(),
        };
        const assistantMessage = {
            id: window.GPT2API.utils.makeId('message'),
            role: 'assistant',
            modality: selectedModality,
            source: sourceMode,
            status: 'processing',
            text: sourceMode === 'local' ? 'Submitting to Local Gateway...' : 'Calling Sub2API...',
            images: [],
            createdAt: new Date().toISOString(),
        };

        updateActiveWindow((item) => ({
            ...item,
            messages: [...item.messages, userMessage, assistantMessage],
        }));
        return assistantMessage.id;
    }, [selectedModality, sourceMode, updateActiveWindow]);

    return {
        conversationWindows,
        activeWindow,
        activeWindowId,
        sourceMode,
        selectedModality,
        sub2apiBaseUrl,
        rememberToken,
        sub2apiToken,
        model,
        n,
        prompt,
        loading,
        error,
        jobMessage,
        apiStatus,
        queueStatus,
        pollRef,
        setActiveWindowId,
        setSourceMode,
        setSelectedModality,
        setSub2apiBaseUrl,
        setRememberToken,
        setSub2apiToken,
        setModel,
        setN,
        setPrompt,
        setLoading,
        setError,
        setJobMessage,
        setApiStatus,
        setQueueStatus,
        updateMessage,
        addWindow,
        deleteWindow,
        renameWindow,
        clearWindow,
        appendPair,
    };
};

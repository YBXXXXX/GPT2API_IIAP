function App() {
    const { useCallback, useEffect } = React;
    const state = window.GPT2API.state.useWorkspaceState();
    const {
        conversationWindows,
        activeWindow,
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
    } = state;

    useEffect(() => {
        window.GPT2API.api.getLocalHealth()
            .then((online) => setApiStatus(online ? 'online' : 'offline'))
            .catch(() => setApiStatus('offline'));

        const interval = setInterval(() => {
            window.GPT2API.api.getQueueStatus()
                .then((data) => setQueueStatus(data))
                .catch(() => {});
        }, 2000);
        return () => clearInterval(interval);
    }, [setApiStatus, setQueueStatus]);

    const finishWithImages = useCallback((assistantMessageId, images, promptText, sourceLabel) => {
        updateMessage(assistantMessageId, {
            status: 'done',
            text: images.length ? `${sourceLabel} returned ${images.length} image(s).` : '未找到可显示的图片结果。',
            images,
            prompt: promptText,
        });
        setLoading(false);
        setJobMessage('');
    }, [setJobMessage, setLoading, updateMessage]);

    const pollLocalResult = useCallback((requestId, assistantMessageId, promptText) => {
        const pollOnce = async () => {
            const data = await window.GPT2API.api.getLocalQueueResult(requestId);

            if (data.status === 'done') {
                const images = window.GPT2API.api.normalizeImageResponse(data.data, promptText);
                finishWithImages(assistantMessageId, images, promptText, 'Local Gateway');
                return true;
            }

            if (data.status === 'error' || data.status === 'not_found') {
                const detail = data.detail || '本地网关任务失败';
                updateMessage(assistantMessageId, { status: 'error', text: detail });
                setError(detail);
                setLoading(false);
                return true;
            }

            if (data.status === 'queued') {
                const position = data.position >= 0 ? data.position + 1 : 1;
                const text = `Local Gateway queue position #${position}`;
                setJobMessage(text);
                updateMessage(assistantMessageId, { status: 'queued', text });
            }

            if (data.status === 'processing') {
                const text = data.message || 'Local Gateway is generating image output.';
                setJobMessage(text);
                updateMessage(assistantMessageId, { status: 'processing', text });
            }

            return false;
        };

        pollOnce().catch((err) => {
            setError(err.message);
            updateMessage(assistantMessageId, { status: 'error', text: err.message });
            setLoading(false);
        });

        pollRef.current = setInterval(async () => {
            try {
                const complete = await pollOnce();
                if (complete && pollRef.current) {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                }
            } catch (err) {
                if (pollRef.current) clearInterval(pollRef.current);
                pollRef.current = null;
                setError(err.message);
                updateMessage(assistantMessageId, { status: 'error', text: err.message });
                setLoading(false);
            }
        }, 1500);
    }, [
        finishWithImages,
        pollRef,
        setError,
        setJobMessage,
        setLoading,
        updateMessage,
    ]);

    const runLocalGateway = async (assistantMessageId, promptText) => {
        const data = await window.GPT2API.api.submitLocalImageGeneration({
            prompt: promptText,
            model,
            n: parseInt(n, 10),
        });
        updateMessage(assistantMessageId, { status: 'queued', text: 'Local Gateway request queued.' });
        pollLocalResult(data.request_id, assistantMessageId, promptText);
    };

    const runSub2api = async (assistantMessageId, promptText) => {
        const data = await window.GPT2API.api.callSub2apiImageGeneration({
            baseUrl: sub2apiBaseUrl,
            token: sub2apiToken,
            prompt: promptText,
            model,
            n: parseInt(n, 10),
        });

        if (data.request_id) {
            updateMessage(assistantMessageId, {
                status: 'queued',
                text: 'Sub2API returned a queued request. Polling this project queue is only available for Local Gateway.',
            });
            setLoading(false);
            setJobMessage('');
            return;
        }

        const images = window.GPT2API.api.normalizeImageResponse(data, promptText);
        if (!images.length) {
            throw new Error('Sub2API response did not include b64_json or url image data');
        }
        finishWithImages(assistantMessageId, images, promptText, 'Sub2API');
    };

    const handleGenerate = useCallback(async () => {
        const promptText = prompt.trim();
        if (!promptText) {
            setError('请输入 Prompt');
            return;
        }
        if (selectedModality !== 'image') {
            setError('当前只实现 Image 调用，Video/Audio 是预留入口');
            return;
        }
        if (loading) return;
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }

        setLoading(true);
        setError('');
        setJobMessage(sourceMode === 'local' ? 'Submitting to Local Gateway...' : 'Calling Sub2API...');
        const assistantMessageId = appendPair(promptText);

        try {
            if (sourceMode === 'local') {
                await runLocalGateway(assistantMessageId, promptText);
            } else {
                await runSub2api(assistantMessageId, promptText);
            }
        } catch (err) {
            const detail = err.message || '调用失败';
            setError(detail);
            setLoading(false);
            setJobMessage('');
            updateMessage(assistantMessageId, { status: 'error', text: detail });
        }
    }, [
        appendPair,
        loading,
        prompt,
        selectedModality,
        sourceMode,
        setError,
        setJobMessage,
        setLoading,
        updateMessage,
    ]);

    const WindowSidebar = window.GPT2API.components.WindowSidebar;
    const MessageList = window.GPT2API.components.MessageList;
    const ComposerPanel = window.GPT2API.components.ComposerPanel;
    const activeMessages = activeWindow?.messages || [];

    return (
        <div className="shell">
            <WindowSidebar
                apiStatus={apiStatus}
                queueStatus={queueStatus}
                conversationWindows={conversationWindows}
                activeWindow={activeWindow}
                loading={loading}
                onAddWindow={addWindow}
                onSelectWindow={setActiveWindowId}
                onRenameWindow={renameWindow}
                onDeleteWindow={deleteWindow}
            />
            <MessageList
                activeWindow={activeWindow}
                activeMessages={activeMessages}
                sourceMode={sourceMode}
                loading={loading}
                onClearWindow={clearWindow}
                onDownloadImage={window.GPT2API.utils.downloadImage}
            />
            <ComposerPanel
                sourceMode={sourceMode}
                sub2apiBaseUrl={sub2apiBaseUrl}
                sub2apiToken={sub2apiToken}
                rememberToken={rememberToken}
                selectedModality={selectedModality}
                model={model}
                n={n}
                prompt={prompt}
                loading={loading}
                jobMessage={jobMessage}
                error={error}
                onSourceModeChange={setSourceMode}
                onSub2apiBaseUrlChange={setSub2apiBaseUrl}
                onSub2apiTokenChange={setSub2apiToken}
                onRememberTokenChange={setRememberToken}
                onSelectedModalityChange={setSelectedModality}
                onModelChange={setModel}
                onCountChange={setN}
                onPromptChange={setPrompt}
                onGenerate={handleGenerate}
            />
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);

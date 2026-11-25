'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { api, type AIProviderPreset, type AISettings } from '@/lib/api';

const MODEL_HINTS: Record<string, string> = {
	ollama: 'Local model (for example, qwen3:4b-instruct)',
	openrouter: 'provider/model (for example, openai/gpt-4o-mini)',
	openai: 'Model ID (for example, gpt-4o-mini)',
	anthropic: 'Model ID (for example, claude-3-5-haiku-latest)',
	google: 'Model ID (for example, gemini-2.5-flash)',
	cohere: 'Model ID (for example, command-r-plus-08-2024)',
	cohere_compat: 'Model ID (for example, command-r-plus-08-2024)',
	deepseek: 'Model ID (for example, deepseek-chat)',
	groq: 'Model ID from Groq',
	mistral: 'Model ID from Mistral',
	together: 'Model ID from Together AI',
	fireworks: 'Model ID from Fireworks AI',
	cerebras: 'Model ID from Cerebras',
	custom: 'Model ID provided by your API host',
};

const DEFAULT_MODELS: Record<string, string> = {
	ollama: 'qwen3:4b-instruct',
	openrouter: 'google/gemma-4-31b-it:free',
	openai: 'gpt-4o-mini',
	anthropic: 'claude-3-5-haiku-latest',
	google: 'gemini-2.5-flash',
	cohere: 'command-r-plus-08-2024',
	cohere_compat: 'command-r-plus-08-2024',
	deepseek: 'deepseek-chat',
	groq: '', mistral: '', together: '', fireworks: '', cerebras: '', custom: '',
};

const MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
	ollama: [
		{ value: 'qwen3:4b-instruct', label: 'Qwen3 4B (default, fast)' },
		{ value: 'qwen2.5-coder:7b-instruct-q4_K_M', label: 'Qwen2.5 Coder 7B (deep check)' },
	],
	openrouter: [
		{ value: 'google/gemma-4-31b-it:free', label: 'Gemma 4 31B (free)' },
		{ value: 'cohere/command-r-plus-08-2024', label: 'Cohere Command R+ (08-2024)' },
	],
	cohere: [
		{ value: 'command-r-plus-08-2024', label: 'Command R+ (08-2024)' },
	],
	cohere_compat: [
		{ value: 'command-r-plus-08-2024', label: 'Command R+ (08-2024)' },
	],
};

export function AIProviderSettingsForm({ showHeading = true }: { showHeading?: boolean }) {
	const router = useRouter();
	const [providers, setProviders] = useState<AIProviderPreset[]>([]);
	const [current, setCurrent] = useState<AISettings | null>(null);
	const [provider, setProvider] = useState('openrouter');
	const [model, setModel] = useState('');
	const [apiKey, setApiKey] = useState('');
	const [baseUrl, setBaseUrl] = useState('');
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState('');
	const [notice, setNotice] = useState('');
	const selectedPreset = useMemo(() => providers.find((item) => item.id === provider), [providers, provider]);
	const isLocal = provider === 'ollama';

	useEffect(() => {
		let active = true;
		Promise.all([api.aiProviders(), api.aiSettings()]).then(([available, saved]) => {
			if (!active) return;
			setProviders(available);
			setCurrent(saved);
			const selected = saved.provider ?? 'openrouter';
			setProvider(selected);
			setModel(saved.model ?? DEFAULT_MODELS[selected] ?? '');
			setBaseUrl(saved.base_url ?? available.find((item) => item.id === selected)?.base_url ?? '');
		}).catch((cause: unknown) => {
			if (!active) return;
			if (cause instanceof Error && cause.message.includes('(401)')) router.replace('/login');
			else setError(cause instanceof Error ? cause.message : 'AI settings could not be loaded.');
		}).finally(() => { if (active) setLoading(false); });
		return () => { active = false; };
	}, [router]);

	function chooseProvider(next: string) {
		setProvider(next);
		setModel(DEFAULT_MODELS[next] ?? '');
		setBaseUrl(providers.find((item) => item.id === next)?.base_url ?? '');
		setApiKey('');
	}

	async function save(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setSaving(true); setError(''); setNotice('');
		try {
			const saved = await api.saveAISettings({
				provider,
				model: model.trim(),
				...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
				...(baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
			});
			setCurrent(saved); setApiKey(''); setNotice('AI provider settings saved.');
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'AI settings could not be saved.');
		} finally { setSaving(false); }
	}

	async function reset() {
		setSaving(true); setError(''); setNotice('');
		try {
			const saved = await api.resetAISettings();
			setCurrent(saved);
			const selected = saved.provider ?? 'openrouter';
			setProvider(selected);
			setModel(saved.model ?? DEFAULT_MODELS[selected] ?? '');
			setBaseUrl(saved.base_url ?? providers.find((item) => item.id === selected)?.base_url ?? '');
			setApiKey('');
			setNotice(saved.using_server_default ? 'Your personal key was removed. The workspace default is active.' : 'Your personal AI provider was removed.');
		} catch (cause) {
			setError(cause instanceof Error ? cause.message : 'AI settings could not be reset.');
		} finally { setSaving(false); }
	}

	if (loading) return <div className="settings-loading"><span className="loading-mark" /><span>Loading AI settings…</span></div>;

	return <div className="ai-provider-settings">
		{showHeading && <div className="ai-provider-heading"><div><div className="eyebrow">MODEL & CONNECTION</div><h2>AI provider</h2></div><span className={current?.api_key_configured ? 'provider-status connected' : 'provider-status'}>{current?.using_server_default ? 'Workspace key' : current?.api_key_configured ? 'Connected' : 'Not connected'}</span></div>}
		{error && <div className="notice" role="alert">{error}</div>}
		{notice && <div className="settings-success" role="status">{notice}</div>}
		<form className="ai-settings-card" onSubmit={(event) => void save(event)}>
			<label className="ai-field"><span>API host</span><select value={provider} onChange={(event) => chooseProvider(event.target.value)}>{providers.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select><small>Use a preset host or any OpenAI-compatible endpoint.</small></label>
			<label className="ai-field"><span>Model ID</span><input list={`model-options-${provider}`} value={model} onChange={(event) => setModel(event.target.value)} placeholder={MODEL_HINTS[provider]} maxLength={200} required /><datalist id={`model-options-${provider}`}>{(MODEL_OPTIONS[provider] ?? []).map((option) => <option value={option.value} label={option.label} key={option.value} />)}</datalist><small>Choose a suggestion or enter the exact model ID from your provider.</small></label>
			{isLocal ? <div className="notice">Ollama runs on this machine. No API key or cloud account is needed; make sure the model is pulled (<code>ollama pull {model || 'qwen3:4b-instruct'}</code>).</div> : <label className="ai-field"><span>API key {current?.api_key_configured && !current.using_server_default && provider === current.provider ? <em>Saved · leave blank to keep it</em> : null}</span><input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={current?.api_key_configured && !current.using_server_default && provider === current.provider ? 'Saved securely' : 'Paste your provider API key'} autoComplete="new-password" maxLength={1000} /><small>Encrypted before storage and never shown again.</small></label>}
			<label className="ai-field"><span>API base URL <em>{provider === 'custom' ? 'Required' : 'Optional override'}</em></span><input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder={selectedPreset?.base_url || 'https://api.example.com/v1'} maxLength={500} required={provider === 'custom'} /><small>Change this only if your API host provides a different endpoint.</small></label>
			<div className="ai-settings-actions"><button className="button button-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save provider'}</button>{current?.api_key_configured && !current.using_server_default && <button className="quiet-button" type="button" onClick={() => void reset()} disabled={saving}>Remove personal key</button>}</div>
		</form>
	</div>;
}

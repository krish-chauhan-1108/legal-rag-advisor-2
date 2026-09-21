import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Clock3,
  KeyRound,
  LockKeyhole,
  Power,
  RefreshCw,
  ShieldCheck,
  Trash2,
  XCircle,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/auth';
import {
  AdminApiError,
  createAdminKey,
  deleteAdminKey,
  getAdminAccess,
  getAdminKeys,
  getAdminUsage,
  updateAdminKey,
} from '../api/admin';
import type { AdminKey, AdminUsageRow, UsageBucket } from '../api/admin';

type AccessState = 'checking' | 'authorized' | 'unauthenticated' | 'forbidden' | 'error';

interface KeyFormState {
  label: string;
  apiKey: string;
  provider: string;
  model: string;
  mode: 'quick' | 'deep';
  baseUrl: string;
  rotationOrder: string;
}

const EMPTY_BUCKET: UsageBucket = { total: 0, success: 0, failure: 0, quota: 0 };

const formatIst = (value?: string | null): string => {
  if (!value) return 'Never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown';
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Kolkata',
  }).format(date) + ' IST';
};

const modelLabel = (model: string): string => {
  const normalized = model.toLowerCase();
  if (normalized.includes('flash') || normalized.includes('quick')) return 'Quick Thinking';
  if (normalized.includes('gemma') || normalized.includes('deep')) return 'Deep Thinking';
  return model;
};

const getErrorText = (error: unknown, fallback: string): string => (
  error instanceof Error ? error.message : fallback
);

const Counter = ({ label, value }: { label: string; value: number }) => (
  <div className="admin-counter">
    <span>{label}</span>
    <strong>{value.toLocaleString('en-IN')}</strong>
  </div>
);

const UsageCard = ({ label, bucket }: { label: string; bucket: UsageBucket }) => (
  <div className="admin-usage-model">
    <div className="admin-usage-model__heading">
      <span>{label}</span>
      <span className="admin-usage-model__total">{bucket.total.toLocaleString('en-IN')} requests</span>
    </div>
    <div className="admin-counter-grid">
      <Counter label="Successful" value={bucket.success} />
      <Counter label="Failed" value={bucket.failure} />
      <Counter label="Quota" value={bucket.quota} />
    </div>
  </div>
);

const AdminKeyRow: React.FC<{
  keyRecord: AdminKey;
  rotationDraft: string;
  isSaving: boolean;
  onRotationChange: (value: string) => void;
  onRotationBlur: () => void;
  onToggle: () => void;
  onDelete: () => void;
}> = ({ keyRecord, rotationDraft, isSaving, onRotationChange, onRotationBlur, onToggle, onDelete }) => (
  <div className="admin-key-row">
    <div className="admin-key-row__identity">
      <div className="admin-key-icon"><KeyRound size={17} /></div>
      <div>
        <div className="admin-key-label">{keyRecord.label}</div>
        <div className="admin-key-mask">{keyRecord.provider} · {keyRecord.model} · {keyRecord.maskedKey}</div>
      </div>
    </div>
    <div className="admin-key-row__meta">
      <label className="admin-field admin-field--compact">
        <span>Order</span>
        <input
          type="number"
          min="1"
          value={rotationDraft}
          onChange={(event) => onRotationChange(event.target.value)}
          onBlur={onRotationBlur}
          disabled={isSaving}
          aria-label={`Rotation order for ${keyRecord.label}`}
        />
      </label>
      <span className={`admin-status-pill ${keyRecord.active ? 'admin-status-pill--active' : 'admin-status-pill--muted'}`}>
        <span className="admin-status-dot" />
        {keyRecord.active ? 'Active' : 'Inactive'}
      </span>
      <span className="admin-key-last-used"><Clock3 size={14} /> {formatIst(keyRecord.lastUsedAt)}</span>
    </div>
    <div className="admin-key-row__actions">
      <button type="button" className="admin-icon-button" onClick={onToggle} disabled={isSaving} title={keyRecord.active ? 'Deactivate key' : 'Activate key'}>
        <Power size={16} />
        <span className="sr-only">{keyRecord.active ? 'Deactivate' : 'Activate'} {keyRecord.label}</span>
      </button>
      <button type="button" className="admin-icon-button admin-icon-button--danger" onClick={onDelete} disabled={isSaving} title="Delete key">
        <Trash2 size={16} />
        <span className="sr-only">Delete {keyRecord.label}</span>
      </button>
    </div>
  </div>
);

export const AdminView: React.FC = () => {
  const navigate = useNavigate();
  const { credential, user } = useAuth();
  const [accessState, setAccessState] = useState<AccessState>(credential ? 'checking' : 'unauthenticated');
  const [keys, setKeys] = useState<AdminKey[]>([]);
  const [usage, setUsage] = useState<AdminUsageRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [form, setForm] = useState<KeyFormState>({ label: '', apiKey: '', provider: 'groq', model: 'openai/gpt-oss-120b', mode: 'quick', baseUrl: '', rotationOrder: '1' });
  const [isAdding, setIsAdding] = useState(false);
  const [savingKeyId, setSavingKeyId] = useState<string | null>(null);
  const [rotationDrafts, setRotationDrafts] = useState<Record<string, string>>({});

  const loadDashboard = useCallback(async (isRefresh = false) => {
    if (!credential) {
      setAccessState('unauthenticated');
      return;
    }

    setAccessState('checking');
    setError(null);
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const access = await getAdminAccess(credential);
      if (!access.authorized) {
        setAccessState('forbidden');
        setKeys([]);
        setUsage([]);
        return;
      }

      const [nextKeys, nextUsage] = await Promise.all([
        getAdminKeys(credential),
        getAdminUsage(credential),
      ]);
      setAccessState('authorized');
      setKeys(nextKeys);
      setUsage(nextUsage);
      setRotationDrafts(Object.fromEntries(nextKeys.map((keyRecord) => [keyRecord.id, String(keyRecord.rotationOrder)])));
    } catch (loadError) {
      if (loadError instanceof AdminApiError && loadError.status === 401) {
        setAccessState('error');
        setError('Your Google session has expired. Sign in again to open the admin console.');
      } else if (loadError instanceof AdminApiError && loadError.status === 403) {
        setAccessState('forbidden');
      } else {
        setAccessState('error');
        setError(getErrorText(loadError, 'The admin console could not be loaded.'));
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [credential]);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) void loadDashboard();
    });
    return () => { active = false; };
  }, [loadDashboard]);

  const usageByKey = useMemo(() => {
    const grouped = new Map<string, Map<string, { label: string; minute: UsageBucket; day: UsageBucket }>>();
    usage.forEach((row) => {
      const current = grouped.get(row.keyId) || new Map([
        ['__quick__', { label: 'Quick Thinking', minute: { ...EMPTY_BUCKET }, day: { ...EMPTY_BUCKET } }],
        ['__deep__', { label: 'Deep Thinking', minute: { ...EMPTY_BUCKET }, day: { ...EMPTY_BUCKET } }],
      ]);
      const label = modelLabel(row.model);
      const modelKey = label === 'Quick Thinking' ? '__quick__' : label === 'Deep Thinking' ? '__deep__' : row.model;
      current.set(modelKey, { label, minute: row.minute, day: row.day });
      grouped.set(row.keyId, current);
    });
    return grouped;
  }, [usage]);

  const updateKey = async (keyRecord: AdminKey, input: { active?: boolean; rotation_order?: number }) => {
    if (!credential) return;
    setSavingKeyId(keyRecord.id);
    setError(null);
    try {
      await updateAdminKey(credential, keyRecord.id, input);
      await loadDashboard(true);
    } catch (updateError) {
      setError(getErrorText(updateError, 'That key could not be updated.'));
    } finally {
      setSavingKeyId(null);
    }
  };

  const handleAddKey = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const label = form.label.trim();
    const apiKey = form.apiKey.trim();
    const rotationOrder = Number(form.rotationOrder);
    if (!label || !apiKey || !Number.isInteger(rotationOrder) || rotationOrder < 1) {
      setFormError('Add a label, API key, and a whole-number rotation order of 1 or higher.');
      return;
    }
    if (!credential) return;

    setFormError(null);
    setError(null);
    setIsAdding(true);
    try {
      await createAdminKey(credential, { label, api_key: apiKey, provider: form.provider, model: form.model, mode: form.mode, ...(form.baseUrl.trim() ? { base_url: form.baseUrl.trim() } : {}), rotation_order: rotationOrder });
      setForm({ label: '', apiKey: '', provider: form.provider, model: form.model, mode: form.mode, baseUrl: form.baseUrl, rotationOrder: String(keys.length + 2) });
      await loadDashboard(true);
    } catch (addError) {
      setFormError(getErrorText(addError, 'That API key could not be added.'));
    } finally {
      // Do not retain the provider secret in React state after the submission attempt.
      setForm((current) => ({ ...current, apiKey: '' }));
      setIsAdding(false);
    }
  };

  const handleDeleteKey = async (keyRecord: AdminKey) => {
    if (!credential || !window.confirm(`Delete ${keyRecord.label}? This cannot be undone.`)) return;
    setSavingKeyId(keyRecord.id);
    setError(null);
    try {
      await deleteAdminKey(credential, keyRecord.id);
      await loadDashboard(true);
    } catch (deleteError) {
      setError(getErrorText(deleteError, 'That key could not be deleted.'));
    } finally {
      setSavingKeyId(null);
    }
  };

  if (accessState === 'unauthenticated') {
    return <AdminState icon={<LockKeyhole size={22} />} title="Sign in to continue" message="The admin console requires a Google account with administrator access." actionLabel="Open account" onAction={() => navigate('/account')} />;
  }

  if (accessState === 'checking') {
    return <AdminState icon={<RefreshCw size={22} className="admin-spin" />} title="Checking admin access" message="Verifying your Google account before opening the private console." actionLabel="Back to chats" onAction={() => navigate('/')} />;
  }

  if (accessState === 'forbidden') {
    return <AdminState icon={<ShieldCheck size={22} />} title="Admin access required" message={`The account ${user?.email || 'currently signed in'} is not on the administrator allowlist.`} actionLabel="Back to chats" onAction={() => navigate('/')} tone="warning" />;
  }

  if (accessState === 'error' && !keys.length) {
    return <AdminState icon={<AlertTriangle size={22} />} title="Admin console unavailable" message={error || 'The admin console could not be loaded.'} actionLabel="Try again" onAction={() => void loadDashboard(true)} tone="warning" />;
  }

  return (
    <div className="admin-page">
      <header className="admin-page__header">
        <div>
          <p className="admin-eyebrow">TRANA operations</p>
          <h2>Admin console</h2>
          <p className="admin-page__subtitle">Manage provider rotation and monitor Quick Thinking capacity.</p>
        </div>
        <button type="button" className="admin-secondary-button" onClick={() => void loadDashboard(true)} disabled={refreshing || loading}>
          <RefreshCw size={15} className={refreshing ? 'admin-spin' : ''} />
          Refresh
        </button>
      </header>

      {error && <div className="admin-alert admin-alert--error"><AlertTriangle size={17} />{error}</div>}

      <div className="admin-page__content">
        <section className="admin-panel admin-panel--intro">
          <div className="admin-panel__icon"><ShieldCheck size={20} /></div>
          <div>
            <p className="admin-panel__kicker">Private workspace</p>
            <h3>{user?.email || 'Authorized administrator'}</h3>
            <p>Only allowlisted Google accounts can view key metadata and usage. Raw provider keys are never shown here.</p>
          </div>
        </section>

        <div className="admin-grid admin-grid--top">
          <section className="admin-panel">
            <div className="admin-section-heading">
              <div>
                <p className="admin-panel__kicker">Rotation pool</p>
                <h3>API keys</h3>
              </div>
              <span className="admin-count-badge">{keys.length} configured</span>
            </div>
            <form className="admin-key-form" onSubmit={(event) => void handleAddKey(event)}>
              <label className="admin-field">
                <span>Label</span>
                <input value={form.label} onChange={(event) => setForm(current => ({ ...current, label: event.target.value }))} placeholder="Primary production key" maxLength={80} />
              </label>
              <label className="admin-field admin-field--wide">
                <span>Provider API key</span>
                <input type="password" value={form.apiKey} onChange={(event) => setForm(current => ({ ...current, apiKey: event.target.value }))} placeholder="Paste a key; it clears after submission" autoComplete="off" spellCheck={false} />
              </label>
              <label className="admin-field">
                <span>Provider</span>
                <select value={form.provider} onChange={(event) => setForm(current => ({ ...current, provider: event.target.value }))}>
                  <option value="groq">Groq</option>
                  <option value="cerebras">Cerebras</option>
                  <option value="nvidia">NVIDIA</option>
                  <option value="google">Google</option>
                  <option value="llama">Llama-compatible</option>
                </select>
              </label>
              <label className="admin-field">
                <span>Model ID</span>
                <input value={form.model} onChange={(event) => setForm(current => ({ ...current, model: event.target.value }))} placeholder="openai/gpt-oss-120b" />
              </label>
              <label className="admin-field">
                <span>Mode</span>
                <select value={form.mode} onChange={(event) => setForm(current => ({ ...current, mode: event.target.value as 'quick' | 'deep' }))}>
                  <option value="quick">Quick Thinking</option>
                  <option value="deep">Deep Thinking</option>
                </select>
              </label>
              <label className="admin-field admin-field--wide">
                <span>Custom base URL (optional)</span>
                <input value={form.baseUrl} onChange={(event) => setForm(current => ({ ...current, baseUrl: event.target.value }))} placeholder="Only for custom OpenAI-compatible endpoints" />
              </label>
              <label className="admin-field admin-field--order">
                <span>Order</span>
                <input type="number" min="1" value={form.rotationOrder} onChange={(event) => setForm(current => ({ ...current, rotationOrder: event.target.value }))} />
              </label>
              <button type="submit" className="admin-primary-button" disabled={isAdding}>
                <KeyRound size={15} />
                {isAdding ? 'Adding…' : 'Add key'}
              </button>
            </form>
            {formError && <p className="admin-form-error"><XCircle size={15} />{formError}</p>}

            <div className="admin-key-list">
              {loading ? (
                <div className="admin-empty-state"><RefreshCw size={17} className="admin-spin" />Loading rotation keys…</div>
              ) : keys.length === 0 ? (
                <div className="admin-empty-state"><KeyRound size={17} />No API keys configured yet.</div>
              ) : (
                keys.map((keyRecord) => (
                  <AdminKeyRow
                    key={keyRecord.id}
                    keyRecord={keyRecord}
                    rotationDraft={rotationDrafts[keyRecord.id] ?? String(keyRecord.rotationOrder)}
                    isSaving={savingKeyId === keyRecord.id}
                    onRotationChange={(value) => setRotationDrafts(current => ({ ...current, [keyRecord.id]: value }))}
                    onRotationBlur={() => {
                      const nextOrder = Number(rotationDrafts[keyRecord.id]);
                      if (Number.isInteger(nextOrder) && nextOrder >= 1 && nextOrder !== keyRecord.rotationOrder) {
                        void updateKey(keyRecord, { rotation_order: nextOrder });
                      }
                    }}
                    onToggle={() => void updateKey(keyRecord, { active: !keyRecord.active })}
                    onDelete={() => void handleDeleteKey(keyRecord)}
                  />
                ))
              )}
            </div>
          </section>

          <section className="admin-panel admin-panel--notes">
            <p className="admin-panel__kicker">Rotation notes</p>
            <h3>Keep the pool healthy.</h3>
            <ul>
              <li><Check size={15} /> Active keys are tried in rotation order.</li>
              <li><Check size={15} /> Deactivate a key before deleting it for a safer pause.</li>
              <li><Check size={15} /> Usage counts reflect TRANA provider attempts, not external AI Studio traffic.</li>
            </ul>
          </section>
        </div>

        <section className="admin-panel">
          <div className="admin-section-heading">
            <div>
              <p className="admin-panel__kicker">Provider telemetry</p>
              <h3>Usage by key</h3>
            </div>
            <span className="admin-timezone">All timestamps and daily buckets use IST</span>
          </div>
          <div className="admin-usage-list">
            {loading ? (
              <div className="admin-empty-state"><RefreshCw size={17} className="admin-spin" />Loading usage…</div>
            ) : keys.length === 0 ? (
              <div className="admin-empty-state">Add an API key to start tracking usage.</div>
            ) : (
              keys.map((keyRecord) => {
                const keyUsage = usageByKey.get(keyRecord.id) || new Map([
                  ['__quick__', { label: 'Quick Thinking', minute: { ...EMPTY_BUCKET }, day: { ...EMPTY_BUCKET } }],
                  ['__deep__', { label: 'Deep Thinking', minute: { ...EMPTY_BUCKET }, day: { ...EMPTY_BUCKET } }],
                ]);
                const modelUsages = Array.from(keyUsage.values());
                return (
                  <article className="admin-usage-card" key={keyRecord.id}>
                    <div className="admin-usage-card__header">
                      <div>
                        <h4>{keyRecord.label}</h4>
                        <span>{keyRecord.maskedKey}</span>
                      </div>
                      <span className={`admin-status-pill ${keyRecord.active ? 'admin-status-pill--active' : 'admin-status-pill--muted'}`}>{keyRecord.active ? 'Active' : 'Inactive'}</span>
                    </div>
                    <div className="admin-usage-periods">
                      <div>
                        <p className="admin-period-label">Current minute</p>
                        {modelUsages.map((modelUsage) => <UsageCard key={`minute-${modelUsage.label}`} label={modelUsage.label} bucket={modelUsage.minute} />)}
                      </div>
                      <div>
                        <p className="admin-period-label">Today · IST</p>
                        {modelUsages.map((modelUsage) => <UsageCard key={`day-${modelUsage.label}`} label={modelUsage.label} bucket={modelUsage.day} />)}
                      </div>
                    </div>
                    <p className="admin-usage-updated">Last request: {formatIst(keyRecord.lastUsedAt)}</p>
                  </article>
                );
              })
            )}
          </div>
          {!loading && usage.length === 0 && keys.length > 0 && <p className="admin-footnote">No usage has been recorded for the configured keys yet.</p>}
        </section>
      </div>
    </div>
  );
};

const AdminState: React.FC<{
  icon: React.ReactNode;
  title: string;
  message: string;
  actionLabel: string;
  onAction: () => void;
  tone?: 'warning';
}> = ({ icon, title, message, actionLabel, onAction, tone }) => (
  <div className="admin-state-page">
    <div className={`admin-state-card ${tone === 'warning' ? 'admin-state-card--warning' : ''}`}>
      <div className="admin-state-icon">{icon}</div>
      <h2>{title}</h2>
      <p>{message}</p>
      <button type="button" className="admin-primary-button" onClick={onAction}>{actionLabel}</button>
    </div>
  </div>
);

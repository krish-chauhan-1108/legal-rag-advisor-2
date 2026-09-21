import { authFetch } from '../auth/auth';
import { API_URL } from '../config';

export interface AdminAccess {
  authorized: boolean;
  email?: string;
}

export interface AdminKey {
  id: string;
  label: string;
  provider: string;
  model: string;
  mode: 'quick' | 'deep' | string;
  baseUrl?: string | null;
  maskedKey: string;
  active: boolean;
  rotationOrder: number;
  status?: string | null;
  lastUsedAt?: string | null;
  lastError?: string | null;
  createdAt?: string | null;
}

export interface UsageBucket {
  total: number;
  success: number;
  failure: number;
  quota: number;
}

export interface AdminUsageRow {
  keyId: string;
  provider: string;
  model: string;
  mode: string;
  minute: UsageBucket;
  day: UsageBucket;
}

export class AdminApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'AdminApiError';
    this.status = status;
  }
}

const getErrorMessage = (payload: unknown, fallback: string): string => {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object' && detail !== null && 'message' in detail) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === 'string') return message;
    }
  }
  if (typeof payload === 'object' && payload !== null && 'message' in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return fallback;
};

const request = async <T>(credential: string, path: string, init?: RequestInit): Promise<T> => {
  const response = await authFetch(`${API_URL}${path}`, credential, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
    cache: 'no-store',
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AdminApiError(
      getErrorMessage(payload, `Admin request failed: ${response.status}`),
      response.status,
    );
  }
  return payload as T;
};

const asRecord = (value: unknown): Record<string, unknown> => (
  typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
);

const firstString = (record: Record<string, unknown>, keys: string[], fallback = ''): string => {
  for (const key of keys) {
    if (typeof record[key] === 'string') return record[key] as string;
  }
  return fallback;
};

const firstNumber = (record: Record<string, unknown>, keys: string[], fallback = 0): number => {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return fallback;
};

const firstBoolean = (record: Record<string, unknown>, keys: string[], fallback = false): boolean => {
  for (const key of keys) {
    if (typeof record[key] === 'boolean') return record[key] as boolean;
  }
  return fallback;
};

const listFromPayload = (payload: unknown, keys: string[]): unknown[] => {
  if (Array.isArray(payload)) return payload;
  const record = asRecord(payload);
  for (const key of keys) {
    if (Array.isArray(record[key])) return record[key] as unknown[];
  }
  return [];
};

export const getAdminAccess = async (credential: string): Promise<AdminAccess> => {
  const payload = await request<unknown>(credential, '/api/admin/access');
  const record = asRecord(payload);
  return {
    authorized: firstBoolean(record, ['authorized', 'is_authorized', 'is_admin', 'allowed']),
    email: firstString(record, ['email', 'user_email'], undefined),
  };
};

export const getAdminKeys = async (credential: string): Promise<AdminKey[]> => {
  const payload = await request<unknown>(credential, '/api/admin/keys');
  return listFromPayload(payload, ['keys', 'items', 'data']).map((item, index) => {
    const record = asRecord(item);
    return {
      id: firstString(record, ['id', 'key_id'], String(index)),
      label: firstString(record, ['label', 'name'], `Gemini key ${index + 1}`),
      provider: firstString(record, ['provider'], 'google'),
      model: firstString(record, ['model', 'model_id', 'model_name'], 'gemini-2.5-flash'),
      mode: firstString(record, ['mode'], 'quick'),
      baseUrl: firstString(record, ['base_url', 'baseUrl'], undefined) || null,
      maskedKey: firstString(record, ['masked_key', 'api_key_masked', 'masked', 'key_display'], '••••••••'),
      active: firstBoolean(record, ['active', 'is_active', 'enabled'], true),
      rotationOrder: firstNumber(record, ['rotation_order', 'order', 'priority'], index + 1),
      status: firstString(record, ['status', 'last_status'], undefined) || null,
      lastUsedAt: firstString(record, ['last_used_at', 'last_used', 'updated_at'], undefined) || null,
      lastError: firstString(record, ['last_error_status', 'last_error', 'error'], undefined) || null,
      createdAt: firstString(record, ['created_at'], undefined) || null,
    };
  });
};

const normalizeBucket = (value: unknown, record: Record<string, unknown>, prefix: string): UsageBucket => {
  const nested = asRecord(value);
  return {
    total: firstNumber(nested, ['total', 'total_requests', 'requests', 'count'], firstNumber(record, [`${prefix}_total`, `${prefix}_total_requests`, `${prefix}_requests`, `${prefix}_count`])),
    success: firstNumber(nested, ['success', 'successful', 'successful_requests'], firstNumber(record, [`${prefix}_success`, `${prefix}_successful`, `${prefix}_successful_requests`])),
    failure: firstNumber(nested, ['failure', 'failed', 'failed_requests', 'errors'], firstNumber(record, [`${prefix}_failure`, `${prefix}_failed`, `${prefix}_failed_requests`, `${prefix}_errors`])),
    quota: firstNumber(nested, ['quota', 'quota_failures', 'rate_limited'], firstNumber(record, [`${prefix}_quota`, `${prefix}_quota_failures`, `${prefix}_rate_limited`])),
  };
};

export const getAdminUsage = async (credential: string): Promise<AdminUsageRow[]> => {
  const payload = await request<unknown>(credential, '/api/admin/usage');
  return listFromPayload(payload, ['rows', 'usage', 'items', 'data']).flatMap((item) => {
    const record = asRecord(item);
    const keyId = firstString(record, ['key_id', 'api_key_id', 'id']);
    if (!keyId) return [];
    return [{
      keyId,
      provider: firstString(record, ['provider'], 'google'),
      model: firstString(record, ['model', 'model_name'], 'unknown'),
      mode: firstString(record, ['mode'], 'quick'),
      minute: normalizeBucket(record.minute, record, 'minute'),
      day: normalizeBucket(record.day, record, 'day'),
    }];
  });
};

export const createAdminKey = (credential: string, input: { label: string; api_key: string; provider: string; model: string; mode: string; base_url?: string; rotation_order: number }) => (
  request<unknown>(credential, '/api/admin/keys', {
    method: 'POST',
    body: JSON.stringify(input),
  })
);

export const updateAdminKey = (credential: string, keyId: string, input: { active?: boolean; rotation_order?: number }) => (
  request<unknown>(credential, `/api/admin/keys/${encodeURIComponent(keyId)}`, {
    method: 'PATCH',
    body: JSON.stringify({
      ...(input.active === undefined ? {} : { is_active: input.active }),
      ...(input.rotation_order === undefined ? {} : { rotation_order: input.rotation_order }),
    }),
  })
);

export const deleteAdminKey = (credential: string, keyId: string) => (
  request<unknown>(credential, `/api/admin/keys/${encodeURIComponent(keyId)}`, { method: 'DELETE' })
);

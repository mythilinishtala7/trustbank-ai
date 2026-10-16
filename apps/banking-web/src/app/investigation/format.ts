import type { TraceEvent } from './investigation.models';

const AGENT_NAMES: Record<string, string> = {
  orchestrator: 'Orchestrator',
  anomaly: 'Anomaly agent',
  fraud_network: 'Fraud network agent',
  questionnaire: 'Questionnaire agent',
  explainer: 'Explainer agent',
  policy: 'Risk policy',
};

export function agentName(id: string): string {
  return AGENT_NAMES[id] ?? id;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}

export type EventSeverity = 'ok' | 'degraded' | 'failed';

export function eventSeverity(e: Pick<TraceEvent, 'type' | 'status'>): EventSeverity {
  if (e.type === 'FAILED' || e.status === 'FAILED' || e.status === 'TIMEOUT') return 'failed';
  if (e.type === 'FALLBACK' || e.status === 'DEGRADED') return 'degraded';
  return 'ok';
}

export function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export function entries(obj: Record<string, unknown> | null | undefined): { key: string; value: string }[] {
  return Object.entries(obj ?? {}).map(([key, value]) => ({ key, value: formatValue(value) }));
}

export type ErrorKind = 'not-found' | 'forbidden' | 'rate-limited' | 'unavailable' | 'error';

export function errorKind(status: number, code: string): ErrorKind {
  if (status === 404 || code === 'NOT_FOUND') return 'not-found';
  if (status === 403 || code === 'FORBIDDEN') return 'forbidden';
  if (status === 429 || code === 'RATE_LIMITED') return 'rate-limited';
  if (status === 503 || status === 0 || code === 'UNAVAILABLE') return 'unavailable';
  return 'error';
}

export const ERROR_MESSAGES: Record<ErrorKind, string> = {
  'not-found': 'Not found.',
  forbidden: 'This session does not have investigator access to this resource.',
  'rate-limited': 'Too many attempts. Please try again later.',
  unavailable: 'The investigation service is temporarily unavailable. Try again shortly.',
  error: 'Something went wrong while loading this data.',
};

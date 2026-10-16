import { Injectable, computed, signal } from '@angular/core';

export const INVESTIGATOR_STORAGE_KEY = 'trustbank.investigator.session';

interface StoredSession {
  token: string;
  expiresAt: string | null;
}

function load(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(INVESTIGATOR_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    return typeof parsed.token === 'string' ? { token: parsed.token, expiresAt: parsed.expiresAt ?? null } : null;
  } catch {
    return null;
  }
}

function expired(s: StoredSession): boolean {
  if (!s.expiresAt) return false;
  const t = Date.parse(s.expiresAt);
  return !Number.isNaN(t) && t <= Date.now();
}

/** Investigator token only. Kept apart from the customer session and never holds the access code. */
@Injectable({ providedIn: 'root' })
export class InvestigatorSession {
  private readonly state = signal<StoredSession | null>(this.initial());

  readonly notice = signal('');
  readonly authenticated = computed(() => this.state() !== null);

  private initial(): StoredSession | null {
    const s = load();
    if (s && expired(s)) {
      sessionStorage.removeItem(INVESTIGATOR_STORAGE_KEY);
      return null;
    }
    return s;
  }

  /** Current token, or null when missing or past its expiry. */
  token(): string | null {
    const s = this.state();
    if (!s) return null;
    if (expired(s)) {
      this.clear('Your investigator session expired. Enter the access code again.');
      return null;
    }
    return s.token;
  }

  signIn(token: string, expiresAt: string | null): void {
    const s: StoredSession = { token, expiresAt };
    sessionStorage.setItem(INVESTIGATOR_STORAGE_KEY, JSON.stringify(s));
    this.notice.set('');
    this.state.set(s);
  }

  clear(notice = ''): void {
    sessionStorage.removeItem(INVESTIGATOR_STORAGE_KEY);
    this.notice.set(notice);
    this.state.set(null);
  }
}

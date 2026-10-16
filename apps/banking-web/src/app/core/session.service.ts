import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import type { AuthResponse } from './models';

export const SESSION_KEY = 'trustbank.customer.session';

interface StoredSession {
  token: string;
  role: 'customer';
  displayName: string;
  expiresAt: string | null;
}

function read(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Partial<StoredSession>;
    if (!s.token || s.role !== 'customer') return null;
    if (s.expiresAt && Date.parse(s.expiresAt) <= Date.now()) return null;
    return { token: s.token, role: 'customer', displayName: s.displayName ?? '', expiresAt: s.expiresAt ?? null };
  } catch {
    return null;
  }
}

/** Customer session only. The investigation console keeps its own, separate token. */
@Injectable({ providedIn: 'root' })
export class SessionService {
  private router = inject(Router);
  private state = signal<StoredSession | null>(read());

  readonly token = computed(() => this.state()?.token ?? null);
  readonly role = computed(() => this.state()?.role ?? null);
  readonly displayName = computed(() => this.state()?.displayName ?? '');
  readonly signedIn = computed(() => this.state() !== null);

  start(auth: AuthResponse): void {
    const s: StoredSession = { token: auth.token, role: 'customer', displayName: auth.displayName, expiresAt: auth.expiresAt ?? null };
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(s));
    this.state.set(s);
  }

  signOut(): void {
    sessionStorage.removeItem(SESSION_KEY);
    this.state.set(null);
  }

  /** Called on a 401: drop the session and go back to the entry screen. */
  expire(): void {
    this.signOut();
    void this.router.navigateByUrl('/enter');
  }
}

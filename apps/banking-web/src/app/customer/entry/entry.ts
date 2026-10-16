import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import type { ApiError, Persona } from '../../core/models';
import { SessionService } from '../../core/session.service';
import { ErrorPanel } from '../ui/error-panel';
import { FocusHeading } from '../ui/focus-heading';

@Component({
  selector: 'app-entry',
  imports: [ErrorPanel, FocusHeading],
  template: `
    <div class="phone entry">
      <h1 appFocusHeading>Welcome to TrustBank</h1>
      <p class="muted">
        TrustBank is a simulated demo. There are no passwords, and no real money, accounts or personal data are involved.
        Pick a profile to continue.
      </p>

      @if (error(); as e) {
        <app-error-panel [error]="e" (retry)="load()" />
      }

      @if (loading()) {
        <p class="muted" role="status">Loading profiles…</p>
      }

      <ul class="persona-list" aria-label="Demo profiles">
        @for (p of personas(); track p.id) {
          <li>
            <button type="button" class="persona" [disabled]="signingIn() !== null" (click)="enter(p)">
              <span class="avatar" aria-hidden="true">{{ initials(p.displayName) }}</span>
              <span class="info">
                <b>{{ p.displayName }}</b>
                <span>{{ p.blurb }}</span>
                <span class="small">{{ p.handle }}</span>
              </span>
              <span class="arrow" aria-hidden="true">→</span>
            </button>
          </li>
        }
      </ul>
      @if (signingIn()) {
        <p class="muted" role="status">Entering as {{ signingIn() }}…</p>
      }
      <p class="simnote">Simulated — hold and authorization are not enforced by a real bank or payment network.</p>
    </div>
  `,
  styles: `
    .persona-list { list-style: none; padding: 0; margin: 24px 0 0; display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    @media (max-width: 700px) { .persona-list { grid-template-columns: 1fr; } }
    .persona { height: 100%; width: 100%; text-align: left; display: flex; align-items: center; gap: 14px; padding: 18px; font: inherit; color: var(--navy); background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); cursor: pointer; box-shadow: var(--shadow-card); transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s; }
    .persona:hover:not(:disabled) { border-color: var(--blue); box-shadow: 0 6px 20px rgba(77, 124, 254, 0.25); transform: translateY(-2px); }
    .persona:disabled { opacity: 0.6; cursor: wait; }
    .avatar { flex: none; width: 46px; height: 46px; border-radius: 50%; background: var(--blue-soft); color: var(--blue-dark); font-weight: 700; font-size: 15px; display: grid; place-items: center; border: 1px solid rgba(77, 124, 254, 0.35); }
    .info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
    .info b { font-size: 16px; }
    .info span { color: var(--muted); font-size: 14px; }
    .arrow { color: var(--blue); font-weight: 700; font-size: 18px; }
  `,
})
export class Entry implements OnInit {
  private api = inject(ApiService);
  private session = inject(SessionService);
  private router = inject(Router);

  readonly personas = signal<Persona[]>([]);
  readonly loading = signal(true);
  readonly error = signal<ApiError | null>(null);
  readonly signingIn = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.personas().subscribe({
      next: (p) => {
        this.personas.set(p);
        this.loading.set(false);
      },
      error: (e: ApiError) => {
        this.error.set(e);
        this.loading.set(false);
      },
    });
  }

  initials(name: string): string {
    return name
      .split(/\s+/)
      .map((w) => w[0])
      .slice(0, 2)
      .join('')
      .toUpperCase();
  }

  enter(p: Persona): void {
    this.error.set(null);
    this.signingIn.set(p.displayName);
    this.api.signIn(p.id).subscribe({
      next: (auth) => {
        this.session.start(auth);
        void this.router.navigateByUrl('/');
      },
      error: (e: ApiError) => {
        this.error.set(e);
        this.signingIn.set(null);
      },
    });
  }
}

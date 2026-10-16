import { CurrencyPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ApiService, newIdempotencyKey } from '../../core/api.service';
import type { ApiError, RecipientLookup } from '../../core/models';
import { ErrorPanel } from '../ui/error-panel';
import { FocusHeading } from '../ui/focus-heading';
import { NOTE_MAX, amountError, recipientError } from './validation';

type Step = 'recipient' | 'amount' | 'review';

@Component({
  selector: 'app-pay-form',
  imports: [CurrencyPipe, RouterLink, ErrorPanel, FocusHeading],
  template: `
    <div class="phone">
      @switch (step()) {
        @case ('recipient') {
          <h1 [appFocusHeading]="step()">Who are you paying?</h1>
          <form class="card" (submit)="$event.preventDefault(); submitRecipient()" novalidate>
            <label for="recipient">UPI ID or account number</label>
            <input
              id="recipient" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" inputmode="email"
              [value]="recipient()" (input)="onRecipient($any($event.target).value)"
              [attr.aria-invalid]="showRecipientError() ? 'true' : null" aria-describedby="recipient-hint recipient-error"
            />
            <p id="recipient-hint" class="muted small hint">For example name&#64;bank, or a 9 to 18 digit account number.</p>
            <p id="recipient-error" class="error" [hidden]="!showRecipientError()" role="alert">{{ recipientMsg() }}</p>

            @if (lookup(); as r) {
              <div class="recipient-card" [class.unverified]="!r.verified" role="status">
                <b>{{ r.found && r.displayName ? r.displayName : 'Unverified recipient' }}</b>
                <span class="small">{{ r.handle }}@if (r.maskedAccount) { · {{ r.maskedAccount }} }</span>
                @if (r.verified) {
                  <span class="verified">Verified recipient</span>
                } @else {
                  <span class="small">We couldn't match this to a known payee. Only continue if you trust this person and have confirmed the details with them.</span>
                }
              </div>
            }
            @if (lookupError(); as e) {
              <app-error-panel [error]="e" (retry)="submitRecipient()" />
            }
            <button type="submit" class="btn" [disabled]="looking()">{{ lookup() ? 'Continue' : looking() ? 'Checking…' : 'Check recipient' }}</button>
            <a class="btn secondary" routerLink="/">Cancel</a>
          </form>
        }
        @case ('amount') {
          <h1 [appFocusHeading]="step()">How much?</h1>
          <form class="card" (submit)="$event.preventDefault(); submitAmount()" novalidate>
            <p class="muted small">To {{ recipientLabel() }}</p>
            <label for="amount">Amount (₹)</label>
            <input
              id="amount" type="number" min="1" step="1" inputmode="numeric"
              [value]="amountText()" (input)="onAmount($any($event.target).value)"
              [attr.aria-invalid]="showAmountError() ? 'true' : null" aria-describedby="amount-error"
            />
            <p id="amount-error" class="error" [hidden]="!showAmountError()" role="alert">{{ amountMsg() }}</p>
            <label for="note">Note (optional)</label>
            <input id="note" type="text" [maxLength]="noteMax" [value]="note()" (input)="note.set($any($event.target).value)" aria-describedby="note-count" />
            <p id="note-count" class="muted small hint">{{ note().length }}/{{ noteMax }}</p>
            <button type="submit" class="btn">Review payment</button>
            <button type="button" class="btn secondary" (click)="goTo('recipient')">Back</button>
          </form>
        }
        @case ('review') {
          <h1 [appFocusHeading]="step()">Review payment</h1>
          <section class="card" aria-label="Payment summary">
            <dl class="receipt">
              <dt>To</dt>
              <dd>{{ recipientLabel() }}<br /><span class="muted small">{{ lookup()?.handle ?? recipient().trim() }}</span></dd>
              <dt>Amount</dt>
              <dd>{{ amount() | currency: 'INR' : 'symbol' : '1.0-0' }}</dd>
              @if (note().trim()) {
                <dt>Note</dt>
                <dd>{{ note().trim() }}</dd>
              }
            </dl>
            @if (busy()) {
              <p class="busy" role="status"><span class="spinner" aria-hidden="true"></span> Checking payment…<br /><span class="muted small">This can take up to 20 seconds. Please keep this page open.</span></p>
            }
            @if (error(); as e) {
              <app-error-panel [error]="e" (retry)="submit()" />
            }
            <button type="button" class="btn" [disabled]="busy()" (click)="submit()">Confirm payment</button>
            <button type="button" class="btn secondary" [disabled]="busy()" (click)="goTo('amount')">Back</button>
          </section>
          <p class="simnote">Simulated — hold and authorization are not enforced by a real bank or payment network.</p>
        }
      }
    </div>
  `,
  styles: `
    .hint { margin-top: 6px; }
    .recipient-card { display: flex; flex-direction: column; gap: 2px; margin-top: 12px; padding: 12px 14px; border: 1px solid rgba(77, 124, 254, 0.45); background: var(--blue-soft); border-radius: 12px; }
    .recipient-card.unverified { border-color: rgba(224, 168, 63, 0.45); background: var(--amber-soft); }
    .verified { color: var(--ok); font-size: 13px; font-weight: 600; }
    .busy { margin: 16px 0 0; display: flex; gap: 10px; align-items: flex-start; font-weight: 600; }
    .spinner { width: 16px; height: 16px; margin-top: 4px; flex: none; border: 2px solid var(--line); border-top-color: var(--blue); border-radius: 50%; animation: spin 0.9s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }
  `,
})
export class PayForm {
  private api = inject(ApiService);
  private router = inject(Router);
  readonly noteMax = NOTE_MAX;

  readonly step = signal<Step>('recipient');
  readonly recipient = signal('');
  readonly recipientTouched = signal(false);
  readonly lookup = signal<RecipientLookup | null>(null);
  readonly looking = signal(false);
  readonly lookupError = signal<ApiError | null>(null);

  readonly amountText = signal('');
  readonly amountTouched = signal(false);
  readonly note = signal('');

  readonly busy = signal(false);
  readonly error = signal<ApiError | null>(null);

  readonly recipientMsg = computed(() => recipientError(this.recipient()));
  readonly showRecipientError = computed(() => this.recipientTouched() && !!this.recipientMsg());
  readonly amount = computed(() => (this.amountText().trim() === '' ? null : Number(this.amountText())));
  readonly amountMsg = computed(() => amountError(this.amount()));
  readonly showAmountError = computed(() => this.amountTouched() && !!this.amountMsg());
  readonly recipientLabel = computed(() => {
    const r = this.lookup();
    return r?.found && r.displayName ? r.displayName : 'Unverified recipient';
  });

  private attemptSignature = '';
  private attemptKey = '';

  onRecipient(v: string): void {
    this.recipient.set(v);
    this.lookup.set(null);
    this.lookupError.set(null);
  }

  onAmount(v: string): void {
    this.amountText.set(v);
  }

  goTo(step: Step): void {
    this.error.set(null);
    this.step.set(step);
  }

  submitRecipient(): void {
    this.recipientTouched.set(true);
    if (this.recipientMsg() || this.looking()) return;
    if (this.lookup()) {
      this.goTo('amount');
      return;
    }
    this.looking.set(true);
    this.lookupError.set(null);
    this.api.lookupRecipient(this.recipient().trim()).subscribe({
      next: (r) => {
        this.lookup.set(r);
        this.looking.set(false);
      },
      error: (e: ApiError) => {
        this.lookupError.set(e);
        this.looking.set(false);
      },
    });
  }

  submitAmount(): void {
    this.amountTouched.set(true);
    if (this.amountMsg()) return;
    this.goTo('review');
  }

  submit(): void {
    const amount = this.amount();
    if (this.busy() || this.recipientMsg() || amount === null || this.amountMsg()) return;
    const recipient = this.recipient().trim();
    const note = this.note().trim();
    const signature = `${recipient}|${amount}|${note}`;
    if (signature !== this.attemptSignature) {
      this.attemptSignature = signature;
      this.attemptKey = newIdempotencyKey();
    }
    this.busy.set(true);
    this.error.set(null);
    this.api.createPayment({ recipient, amount, ...(note ? { note } : {}) }, this.attemptKey).subscribe({
      next: (payment) => {
        this.busy.set(false);
        void this.router.navigate(['/pay', payment.id], { state: { payment } });
      },
      error: (e: ApiError) => {
        this.busy.set(false);
        this.error.set(e);
      },
    });
  }
}

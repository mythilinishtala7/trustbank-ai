import { CurrencyPipe, NgTemplateOutlet } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService, errorMessage } from '../api.service';
import type { Payment, PromisedBenefit, RiskSignal, Scenario, SourceOfDetails } from '../models';

@Component({
  selector: 'app-pay',
  imports: [FormsModule, CurrencyPipe, NgTemplateOutlet, RouterLink],
  templateUrl: './pay.html',
})
export class Pay implements OnInit, OnDestroy {
  private api = inject(ApiService);
  private router = inject(Router);

  scenarios = signal<Scenario[]>([]);
  recipient = signal('');
  amount = signal<number | null>(null);
  note = signal('');
  recipientName = signal('');
  recipientError = signal('');

  payment = signal<Payment | null>(null);
  source = signal<SourceOfDetails | ''>('');
  promise = signal<PromisedBenefit | ''>('');
  pin = signal('');

  busy = signal(false);
  error = signal('');
  remaining = signal(0);
  private timer?: ReturnType<typeof setInterval>;

  status = computed(() => this.payment()?.status ?? 'FORM');
  topSignals = computed<RiskSignal[]>(() =>
    (this.payment()?.assessment.signals ?? []).filter((s) => s.severity !== 'info' || s.points > 0),
  );
  countdown = computed(() => {
    const s = this.remaining();
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  });
  answersReady = computed(() => !!this.source() && !!this.promise());

  ngOnInit(): void {
    this.api.scenarios().subscribe({ next: (s) => this.scenarios.set(s), error: () => undefined });
  }

  ngOnDestroy(): void {
    clearInterval(this.timer);
  }

  useScenario(s: Scenario): void {
    this.recipient.set(s.handle);
    this.amount.set(s.amount);
    this.note.set(s.note);
    this.verifyRecipient();
  }

  verifyRecipient(): void {
    this.recipientName.set('');
    this.recipientError.set('');
    const q = this.recipient().trim();
    if (!q) return;
    this.api.lookup(q).subscribe({
      next: (r) => this.recipientName.set(`${r.displayName} · ${r.bankLabel}`),
      error: (e) => this.recipientError.set(errorMessage(e)),
    });
  }

  private run(call: ReturnType<ApiService['createPayment']>): void {
    this.busy.set(true);
    this.error.set('');
    call.subscribe({
      next: (p) => {
        this.setPayment(p);
        this.busy.set(false);
      },
      error: (e) => {
        this.error.set(errorMessage(e));
        this.busy.set(false);
      },
    });
  }

  private setPayment(p: Payment): void {
    this.payment.set(p);
    clearInterval(this.timer);
    if (p.status === 'HOLD' && p.holdUntil) {
      const tick = () => this.remaining.set(Math.max(0, Math.ceil((new Date(p.holdUntil!).getTime() - Date.now()) / 1000)));
      tick();
      this.timer = setInterval(tick, 500);
    }
  }

  submit(): void {
    const amt = this.amount();
    if (!this.recipient().trim() || !amt || amt < 1) {
      this.error.set('Enter a recipient and an amount.');
      return;
    }
    this.run(this.api.createPayment({ recipient: this.recipient(), amount: amt, note: this.note() }));
  }

  submitAnswers(): void {
    const p = this.payment();
    if (!p || !this.source() || !this.promise()) return;
    this.run(
      this.api.submitAnswers(p.id, {
        sourceOfDetails: this.source() as SourceOfDetails,
        promisedBenefit: this.promise() as PromisedBenefit,
      }),
    );
  }

  continuePayment(): void {
    this.run(this.api.continuePayment(this.payment()!.id));
  }

  authorize(): void {
    this.run(this.api.authorize(this.payment()!.id, this.pin()));
    this.pin.set('');
  }

  cancel(): void {
    this.run(this.api.cancel(this.payment()!.id));
  }

  done(): void {
    this.router.navigateByUrl('/');
  }
}

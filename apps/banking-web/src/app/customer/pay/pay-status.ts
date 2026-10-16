import { CurrencyPipe, DatePipe, NgTemplateOutlet } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable } from 'rxjs';
import { ApiService } from '../../core/api.service';
import type { Answer, ApiError, CustomerPayment, PaymentAction } from '../../core/models';
import { ErrorPanel } from '../ui/error-panel';
import { FocusHeading } from '../ui/focus-heading';
import { Explanation } from './explanation';
import { HoldCountdown } from './hold-countdown';
import { PinEntry } from './pin-entry';
import { Questionnaire } from './questionnaire';

const POLL_MS = 1500;
const REFETCH_RETRY_MS = 1000;

const TITLES: Record<CustomerPayment['status'], string> = {
  INITIATED: 'Checking your payment',
  ASSESSING: 'Checking your payment',
  QUESTIONNAIRE: 'A few quick questions',
  REVIEW: 'Please review before you continue',
  HOLD_ACTIVE: "We've paused this payment",
  HOLD_EXPIRED: 'The pause has ended',
  READY_FOR_AUTH: 'Enter your PIN',
  COMPLETED: 'Payment complete',
  CANCELLED: 'Payment cancelled',
};

@Component({
  selector: 'app-pay-status',
  imports: [CurrencyPipe, DatePipe, NgTemplateOutlet, RouterLink, ErrorPanel, FocusHeading, Explanation, HoldCountdown, PinEntry, Questionnaire],
  templateUrl: './pay-status.html',
  styleUrl: './pay-status.css',
})
export class PayStatus implements OnDestroy {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  readonly payment = signal<CustomerPayment | null>(null);
  readonly loadError = signal<ApiError | null>(null);
  readonly actionError = signal<ApiError | null>(null);
  readonly busy = signal(false);
  readonly acknowledged = signal(false);

  readonly title = computed(() => {
    const p = this.payment();
    return p ? TITLES[p.status] : 'Payment';
  });

  private id = '';
  private poller?: ReturnType<typeof setInterval>;
  private expiryTimer?: ReturnType<typeof setTimeout>;
  private expiryFetches = 0;

  constructor() {
    const handed = this.router.getCurrentNavigation()?.extras.state?.['payment'] as CustomerPayment | undefined;
    if (handed) {
      this.payment.set(handed);
      this.syncPolling();
    }
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((m) => {
      this.id = m.get('id') ?? '';
      if (this.payment()?.id !== this.id) this.payment.set(null);
      this.acknowledged.set(false);
      this.refetch();
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
    clearTimeout(this.expiryTimer);
  }

  can(action: PaymentAction): boolean {
    return !!this.payment()?.actions.includes(action);
  }

  refetch(): void {
    this.loadError.set(null);
    this.api.payment(this.id).subscribe({
      next: (p) => this.apply(p),
      error: (e: ApiError) => {
        if (!this.payment()) this.loadError.set(e);
        else if (e.kind !== 'network' && e.kind !== 'unavailable') this.actionError.set(e);
      },
    });
  }

  submitAnswers(answers: Answer[]): void {
    this.run(this.api.answer(this.id, answers));
  }

  acknowledge(): void {
    if (!this.acknowledged()) return;
    this.run(this.api.acknowledge(this.id));
  }

  verify(): void {
    this.run(this.api.verify(this.id));
  }

  proceed(): void {
    this.run(this.api.continue(this.id));
  }

  cancel(): void {
    this.run(this.api.cancel(this.id));
  }

  authorize(pin: string): void {
    this.run(this.api.authorize(this.id, pin));
  }

  /** Countdown reached zero: ask the server for the real state (never advance locally). */
  onHoldEnded(): void {
    if (this.expiryTimer) return;
    const delay = this.expiryFetches++ === 0 ? 0 : REFETCH_RETRY_MS;
    this.expiryTimer = setTimeout(() => {
      this.expiryTimer = undefined;
      this.refetch();
    }, delay);
  }

  private run(call: Observable<CustomerPayment>): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.actionError.set(null);
    call.subscribe({
      next: (p) => {
        this.busy.set(false);
        this.apply(p);
      },
      error: (e: ApiError) => {
        this.busy.set(false);
        this.actionError.set(e);
        // The server is the source of truth; a conflict means our view of the state is stale.
        if (e.kind === 'conflict') this.refetch();
      },
    });
  }

  private apply(p: CustomerPayment): void {
    if (p.id !== this.id) return;
    if (this.payment()?.status !== p.status) {
      this.acknowledged.set(false);
      this.expiryFetches = 0;
      this.actionError.set(null);
    }
    this.payment.set(p);
    this.syncPolling();
  }

  private syncPolling(): void {
    const status = this.payment()?.status;
    const assessing = status === 'ASSESSING' || status === 'INITIATED';
    if (assessing && !this.poller) {
      this.poller = setInterval(() => this.refetch(), POLL_MS);
    } else if (!assessing) {
      this.stopPolling();
    }
  }

  private stopPolling(): void {
    clearInterval(this.poller);
    this.poller = undefined;
  }
}

import { Component, OnDestroy, OnInit, computed, effect, input, output, signal, untracked } from '@angular/core';
import type { CustomerPayment } from '../../core/models';

/**
 * Counts down to the server's `holdUntil`. The client clock is not trusted: the offset between the
 * server's `serverTime` and the client clock is measured when the payload arrives and applied to every tick.
 */
@Component({
  selector: 'app-hold-countdown',
  template: `
    <div class="countdown-box">
      <p class="muted small">Time remaining</p>
      <div class="countdown" role="timer" aria-label="Time remaining in the pause">{{ display() }}</div>
      <p class="sr-only" aria-live="polite">{{ announcement() }}</p>
    </div>
  `,
  styles: `
    .countdown-box { text-align: center; margin: 8px 0 16px; }
    .countdown-box p { margin: 0; }
  `,
})
export class HoldCountdown implements OnInit, OnDestroy {
  readonly payment = input.required<CustomerPayment>();
  readonly ended = output();

  private remainingMs = signal<number | null>(null);
  private holdEnd: number | null = null;
  private offset = 0;
  private emitted = false;
  private timer?: ReturnType<typeof setInterval>;

  readonly seconds = computed(() => {
    const ms = this.remainingMs();
    return ms === null ? null : Math.max(0, Math.ceil(ms / 1000));
  });
  readonly display = computed(() => {
    const s = this.seconds();
    return s === null ? '–:––' : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  });
  // Updated every 30 seconds (and at zero) so screen readers are not flooded.
  readonly announcement = computed(() => {
    const s = this.seconds();
    if (s === null) return '';
    if (s === 0) return 'The pause has ended.';
    const bucket = Math.ceil(s / 30) * 30;
    return `About ${bucket >= 60 && bucket % 60 === 0 ? `${bucket / 60} minute${bucket === 60 ? '' : 's'}` : `${bucket} seconds`} remaining.`;
  });

  constructor() {
    effect(() => {
      const p = this.payment();
      untracked(() => {
        const serverNow = Date.parse(p.serverTime);
        this.offset = Number.isNaN(serverNow) ? 0 : serverNow - Date.now();
        this.holdEnd = p.holdUntil ? Date.parse(p.holdUntil) : null;
        this.emitted = false;
        this.tick();
      });
    });
  }

  ngOnInit(): void {
    this.timer = setInterval(() => this.tick(), 250);
  }

  ngOnDestroy(): void {
    clearInterval(this.timer);
  }

  private tick(): void {
    if (this.holdEnd === null || Number.isNaN(this.holdEnd)) {
      this.remainingMs.set(null);
      return;
    }
    const left = this.holdEnd - (Date.now() + this.offset);
    this.remainingMs.set(Math.max(0, left));
    if (left <= 0 && !this.emitted) {
      this.emitted = true;
      this.ended.emit();
    }
  }
}

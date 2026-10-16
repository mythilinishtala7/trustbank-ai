import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import type { ApiError, Me } from '../../core/models';
import { ErrorPanel } from '../ui/error-panel';
import { FocusHeading } from '../ui/focus-heading';

@Component({
  selector: 'app-home',
  imports: [RouterLink, CurrencyPipe, DatePipe, ErrorPanel, FocusHeading],
  template: `
    <div class="dash">
      @if (error(); as e) {
        <h1 appFocusHeading>Home</h1>
        <app-error-panel [error]="e" (retry)="load()" />
      } @else if (me(); as m) {
        <div class="dash-grid">
        <section class="card balance" aria-labelledby="home-title">
          <h1 id="home-title" appFocusHeading class="greeting">Hello, {{ m.displayName }}</h1>
          <p class="muted small">{{ m.handle }}</p>
          <p class="muted">Available balance</p>
          <div class="amount" aria-label="Balance">{{ m.balance | currency: 'INR' : 'symbol' : '1.0-0' }}</div>
          <a class="btn light" routerLink="/pay">Pay</a>
        </section>

        <section class="card" aria-labelledby="recent-title">
          <h2 id="recent-title">Recent transactions</h2>
          @for (t of m.recentTransactions; track t.id) {
            <div class="txn">
              <div>
                <div>{{ t.recipientName }}</div>
                <div class="muted small">{{ t.note || 'Payment' }} · {{ t.timestamp | date: 'd MMM, h:mm a' }}</div>
              </div>
              <div class="out">−{{ t.amount | currency: 'INR' : 'symbol' : '1.0-0' }}</div>
            </div>
          } @empty {
            <p class="muted">No transactions yet. Payments you make will appear here.</p>
          }
        </section>
        </div>
        <p class="simnote">Simulated demo data. No real money moves.</p>
      } @else {
        <h1 appFocusHeading>Home</h1>
        <p class="muted" role="status">Loading your account…</p>
      }
    </div>
  `,
  styles: `
    .greeting { font-size: 21px; color: #fff; letter-spacing: -0.01em; }
  `,
})
export class Home implements OnInit {
  private api = inject(ApiService);
  readonly me = signal<Me | null>(null);
  readonly error = signal<ApiError | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.error.set(null);
    this.api.me().subscribe({
      next: (m) => this.me.set(m),
      error: (e: ApiError) => this.error.set(e),
    });
  }
}

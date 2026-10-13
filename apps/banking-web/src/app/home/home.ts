import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService, errorMessage } from '../api.service';
import type { MeResponse } from '../models';

@Component({
  selector: 'app-home',
  imports: [RouterLink, CurrencyPipe, DatePipe],
  template: `
    <div class="phone">
      @if (error()) {
        <p class="error" role="alert">{{ error() }}</p>
      }
      @if (me(); as m) {
        <section class="card balance" aria-label="Account balance">
          <p class="muted">Hello, {{ m.customer.displayName }}</p>
          <div class="amount">{{ m.customer.balance | currency: 'INR' : 'symbol' : '1.0-0' }}</div>
          <p class="muted small">{{ m.customer.upiHandle }}</p>
          <a class="btn secondary" routerLink="/pay">Pay</a>
        </section>

        <section class="card" aria-label="Recent transactions">
          <h2>Recent transactions</h2>
          @for (t of m.transactions.slice(0, 10); track t.id) {
            <div class="txn">
              <div>
                <div>{{ t.beneficiary?.displayName ?? t.beneficiaryId }}</div>
                <div class="muted small">{{ t.note || 'Payment' }} · {{ t.timestamp | date: 'd MMM, h:mm a' }}</div>
              </div>
              <div class="out">−{{ t.amount | currency: 'INR' : 'symbol' : '1.0-0' }}</div>
            </div>
          }
        </section>
        <p class="simnote">Simulated data. Agent mode: {{ m.agentProvider === 'gemini' ? 'Gemini (ADK)' : 'mock (no API key needed)' }}.</p>
      } @else if (!error()) {
        <p class="muted">Loading…</p>
      }
    </div>
  `,
})
export class Home implements OnInit {
  private api = inject(ApiService);
  me = signal<MeResponse | null>(null);
  error = signal('');

  ngOnInit(): void {
    this.api.me().subscribe({
      next: (m) => this.me.set(m),
      error: (e) => this.error.set(errorMessage(e)),
    });
  }
}

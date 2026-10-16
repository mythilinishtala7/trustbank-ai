import { CurrencyPipe, DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ERROR_MESSAGES, ErrorKind, errorKind } from './format';
import { InvestigationApi, InvestigationApiError } from './investigation.api';
import type { TransactionListItem } from './investigation.models';
import { SearchForm } from './search-form';

@Component({
  selector: 'inv-search-page',
  imports: [CurrencyPipe, DatePipe, RouterLink, SearchForm],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1>Find a transaction</h1>
    <section class="inv-card">
      <inv-search-form />
    </section>

    <section class="inv-card" aria-labelledby="recent-heading">
      <h2 id="recent-heading">Recent payments</h2>
      @if (loading()) {
        <p class="inv-muted" role="status">Loading recent payments…</p>
      } @else if (error(); as e) {
        <p class="inv-notice" role="alert">{{ e }} <button type="button" class="inv-btn small" (click)="load()">Retry</button></p>
      } @else if (items().length === 0) {
        <p class="inv-empty">No payments yet. Make a payment in the customer app, or search for a historical transaction id such as <code>txn_hist_1</code>.</p>
      } @else {
        <div class="scroll">
          <table class="inv-table">
            <caption class="inv-sr">Recent simulated payments, newest first</caption>
            <thead>
              <tr><th scope="col">Transaction</th><th scope="col">Customer</th><th scope="col">Recipient</th><th scope="col">Amount</th><th scope="col">Status</th><th scope="col">Created</th></tr>
            </thead>
            <tbody>
              @for (t of items(); track t.transactionId) {
                <tr>
                  <th scope="row"><a [routerLink]="['/investigation', 'transactions', t.transactionId]">{{ t.transactionId }}</a></th>
                  <td>{{ t.customerName }}</td>
                  <td>{{ t.recipientName }}</td>
                  <td>{{ t.amount | currency: 'INR' : 'symbol' : '1.0-0' }}</td>
                  <td>{{ t.status }}</td>
                  <td>{{ t.createdAt | date: 'dd MMM, HH:mm' }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>
  `,
  styles: `
    .scroll { overflow-x: auto; }
  `,
})
export class SearchPage implements OnInit {
  private readonly api = inject(InvestigationApi);
  protected readonly items = signal<TransactionListItem[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal('');

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set('');
    this.api.recent(20).subscribe({
      next: (list) => {
        this.items.set(list);
        this.loading.set(false);
      },
      error: (e: unknown) => {
        this.loading.set(false);
        const err = e instanceof InvestigationApiError ? e : new InvestigationApiError(0, 'ERROR', '');
        const kind: ErrorKind = errorKind(err.status, err.code);
        this.error.set(ERROR_MESSAGES[kind === 'not-found' ? 'error' : kind]);
      },
    });
  }
}

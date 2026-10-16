import { CurrencyPipe, DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, signal, untracked } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { Subscription, map } from 'rxjs';
import { EvidencePanel } from './evidence-panel';
import { ERROR_MESSAGES, ErrorKind, errorKind } from './format';
import { GraphView } from './graph-view';
import { InvestigationApi, InvestigationApiError } from './investigation.api';
import { TransactionDetail, buildEvidenceIndex, isInFlight } from './investigation.models';
import { SearchForm } from './search-form';
import { TimelineFeed } from './timeline-feed';
import { TimelineView } from './timeline-view';

type PageState = 'loading' | 'ready' | ErrorKind;

@Component({
  selector: 'inv-transaction-page',
  imports: [CurrencyPipe, DatePipe, EvidencePanel, GraphView, SearchForm, TimelineView],
  providers: [TimelineFeed],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './transaction-page.html',
  styleUrl: './transaction-page.css',
})
export class TransactionPage {
  private readonly api = inject(InvestigationApi);
  protected readonly feed = inject(TimelineFeed);

  protected readonly id = toSignal(inject(ActivatedRoute).paramMap.pipe(map((p) => p.get('id') ?? '')), { initialValue: '' });
  protected readonly state = signal<PageState>('loading');
  protected readonly detail = signal<TransactionDetail | null>(null);
  protected readonly message = signal('');
  protected readonly focusId = signal<string | null>(null);

  protected readonly evidenceIndex = computed(() => buildEvidenceIndex(this.detail()?.assessments ?? []));
  protected readonly liveStatus = computed(() => this.feed.paymentStatus() ?? this.detail()?.summary.status ?? '');
  protected readonly inFlight = computed(() => isInFlight(this.liveStatus()));
  protected readonly historical = computed(() => this.detail()?.kind === 'HISTORICAL');

  private loading?: Subscription;

  constructor() {
    effect(() => {
      const id = this.id();
      if (id) untracked(() => this.load(id));
    });
    effect(() => {
      const rev = this.feed.stateRevision();
      if (rev > 0) untracked(() => this.refresh());
    });
    inject(DestroyRef).onDestroy(() => {
      this.loading?.unsubscribe();
      this.feed.stop();
    });
  }

  protected load(id = this.id()): void {
    this.loading?.unsubscribe();
    this.feed.stop();
    this.state.set('loading');
    this.detail.set(null);
    this.focusId.set(null);
    this.loading = this.api.transaction(id).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.state.set('ready');
        if (d.kind === 'PAYMENT') this.feed.start(d.transactionId, d.summary.status);
      },
      error: (e: unknown) => this.fail(e),
    });
  }

  private refresh(): void {
    const id = this.id();
    if (!id || this.state() !== 'ready') return;
    this.loading?.unsubscribe();
    this.loading = this.api.transaction(id).subscribe({ next: (d) => this.detail.set(d), error: () => undefined });
  }

  private fail(e: unknown): void {
    const err = e instanceof InvestigationApiError ? e : new InvestigationApiError(0, 'ERROR', '');
    const kind = errorKind(err.status, err.code);
    this.message.set(ERROR_MESSAGES[kind]);
    this.state.set(kind);
  }
}

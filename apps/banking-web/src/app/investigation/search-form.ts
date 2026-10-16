import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { Router } from '@angular/router';

@Component({
  selector: 'inv-search-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <form class="search" role="search" (submit)="submit($event, q)">
      <label for="inv-txn-id">Transaction ID</label>
      <div class="row">
        <input #q id="inv-txn-id" name="txn" type="text" autocomplete="off" spellcheck="false" placeholder="e.g. txn_ab12cd34 or txn_hist_1" [value]="initial()" aria-describedby="inv-txn-help" />
        <button type="submit" class="inv-btn primary">Investigate</button>
      </div>
      <p id="inv-txn-help" class="inv-muted">A payment reference or a historical transaction id. Only the bounded neighbourhood of that transaction is loaded.</p>
      <p class="inv-error" role="alert">{{ error() }}</p>
    </form>
  `,
  styles: `
    .row { display: flex; gap: 8px; }
    .row input { flex: 1; }
    .inv-error:empty { display: none; }
  `,
})
export class SearchForm {
  readonly initial = input('');
  private readonly router = inject(Router);
  protected readonly error = signal('');

  protected submit(event: Event, input: HTMLInputElement): void {
    event.preventDefault();
    const id = input.value.trim();
    if (!id) {
      this.error.set('Enter a transaction id.');
      return;
    }
    this.error.set('');
    void this.router.navigate(['/investigation', 'transactions', id]);
  }
}

import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { ERROR_MESSAGES, errorKind } from './format';
import { InvestigationApi, InvestigationApiError } from './investigation.api';
import { InvestigatorSession } from './investigator-session';

@Component({
  selector: 'inv-gate',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="inv-card gate" aria-labelledby="gate-heading">
      <h1 id="gate-heading">Investigation console</h1>
      <p class="inv-muted">
        Internal tool for reviewing simulated payment assessments. Enter the demo access code to continue. All data here is
        simulated demo data.
      </p>
      @if (session.notice()) {
        <p class="inv-notice" role="status">{{ session.notice() }}</p>
      }
      <form (submit)="submit($event, code)" novalidate>
        <label for="inv-code">Access code</label>
        <input #code id="inv-code" name="inv-code" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" [attr.aria-invalid]="error() ? 'true' : null" aria-describedby="inv-code-error" />
        <p id="inv-code-error" class="inv-error" role="alert">{{ error() }}</p>
        <button type="submit" class="inv-btn primary" [disabled]="busy()">{{ busy() ? 'Checking…' : 'Unlock console' }}</button>
      </form>
    </section>
  `,
  styles: `
    .gate { max-width: 420px; margin: 48px auto; }
    form { margin-top: 12px; }
    .inv-error:empty { display: none; }
  `,
})
export class Gate {
  protected readonly session = inject(InvestigatorSession);
  private readonly api = inject(InvestigationApi);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly busy = signal(false);
  protected readonly error = signal('');

  protected submit(event: Event, input: HTMLInputElement): void {
    event.preventDefault();
    const code = input.value.trim();
    input.value = '';
    if (!code) {
      this.error.set('Enter the access code.');
      return;
    }
    this.busy.set(true);
    this.error.set('');
    this.api.authenticate(code).subscribe({
      next: () => {
        this.busy.set(false);
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
        if (returnUrl?.startsWith('/investigation/')) void this.router.navigateByUrl(returnUrl);
        else void this.router.navigate(['/investigation'], { replaceUrl: true });
      },
      error: (e: unknown) => {
        this.busy.set(false);
        const err = e instanceof InvestigationApiError ? e : new InvestigationApiError(0, 'ERROR', '');
        const kind = errorKind(err.status, err.code);
        this.error.set(err.status === 401 ? 'That access code was not accepted.' : kind === 'rate-limited' || kind === 'unavailable' ? ERROR_MESSAGES[kind] : ERROR_MESSAGES.error);
      },
    });
  }
}

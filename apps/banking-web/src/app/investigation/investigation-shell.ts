import { ChangeDetectionStrategy, Component, ViewEncapsulation, inject } from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
import { InvestigatorSession } from './investigator-session';

@Component({
  selector: 'inv-shell',
  imports: [RouterOutlet, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="inv-shell">
      <header class="inv-top">
        <a routerLink="/investigation" class="inv-brand">TrustBank <span>Investigation console</span></a>
        <span class="inv-sim" title="All entities, amounts and relationships are fictional">Simulated demo data</span>
        <span class="inv-spacer"></span>
        @if (session.authenticated()) {
          <button type="button" class="inv-btn small" (click)="signOut()">Sign out</button>
        }
      </header>
      <main class="inv-main" id="inv-main">
        <router-outlet />
      </main>
      <footer class="inv-foot">
        Internal demo tool. Connections and signals are evidence to investigate, not proof. Not a real bank or payment network.
      </footer>
    </div>
  `,
  styleUrl: './investigation.css',
})
export class InvestigationShell {
  protected readonly session = inject(InvestigatorSession);
  private readonly router = inject(Router);

  protected signOut(): void {
    this.session.clear();
    void this.router.navigate(['/investigation']);
  }
}

import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
import { SessionService } from '../core/session.service';

@Component({
  selector: 'app-customer-shell',
  imports: [RouterOutlet, RouterLink],
  template: `
    <header class="topbar">
      <a class="brand" routerLink="/">TrustBank</a>
      <span class="sim-badge">Simulated demo · no real money</span>
      @if (session.signedIn()) {
        <button type="button" class="link-btn" (click)="signOut()">Sign out</button>
      }
    </header>
    <main class="customer-main"><router-outlet /></main>
  `,
  styles: `
    .topbar { justify-content: space-between; gap: 12px; }
    .sim-badge { margin-left: auto; }
  `,
})
export class CustomerShell {
  protected session = inject(SessionService);
  private router = inject(Router);

  signOut(): void {
    this.session.signOut();
    void this.router.navigateByUrl('/enter');
  }
}

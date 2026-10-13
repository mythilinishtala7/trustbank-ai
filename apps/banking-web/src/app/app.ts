import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <header class="topbar">
      <a class="brand" routerLink="/">TrustBank</a>
      <nav aria-label="Primary">
        <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: false }">Customer app</a>
        <a routerLink="/investigator" routerLinkActive="active">Investigator view</a>
      </nav>
      <span class="sim-badge">Simulated demo · no real money</span>
    </header>
    <main><router-outlet /></main>
  `,
})
export class App {}

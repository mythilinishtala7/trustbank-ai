import { Routes } from '@angular/router';
import { customerGuard, entryGuard } from '../core/guards';
import { CustomerShell } from './customer-shell';

export const CUSTOMER_ROUTES: Routes = [
  {
    path: '',
    component: CustomerShell,
    children: [
      { path: 'enter', canActivate: [entryGuard], title: 'Choose a demo profile · TrustBank', loadComponent: () => import('./entry/entry').then((m) => m.Entry) },
      { path: '', pathMatch: 'full', canActivate: [customerGuard], title: 'Home · TrustBank', loadComponent: () => import('./home/home').then((m) => m.Home) },
      { path: 'pay', canActivate: [customerGuard], title: 'Pay · TrustBank', loadComponent: () => import('./pay/pay-form').then((m) => m.PayForm) },
      { path: 'pay/:id', canActivate: [customerGuard], title: 'Payment · TrustBank', loadComponent: () => import('./pay/pay-status').then((m) => m.PayStatus) },
    ],
  },
];

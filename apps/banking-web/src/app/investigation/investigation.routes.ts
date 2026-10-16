import { Routes } from '@angular/router';
import { investigatorGuard } from './investigator.guard';

export const INVESTIGATION_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./investigation-shell').then((m) => m.InvestigationShell),
    children: [
      { path: '', pathMatch: 'full', loadComponent: () => import('./landing').then((m) => m.Landing) },
      {
        path: 'transactions/:id',
        canActivate: [investigatorGuard],
        loadComponent: () => import('./transaction-page').then((m) => m.TransactionPage),
      },
      { path: '**', redirectTo: '' },
    ],
  },
];

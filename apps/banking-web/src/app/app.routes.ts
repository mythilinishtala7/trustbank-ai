import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: 'investigation',
    loadChildren: () => import('./investigation/investigation.routes').then((m) => m.INVESTIGATION_ROUTES),
  },
  { path: '', loadChildren: () => import('./customer/customer.routes').then((m) => m.CUSTOMER_ROUTES) },
  { path: '**', redirectTo: '' },
];

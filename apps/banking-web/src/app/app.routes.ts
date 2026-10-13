import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./home/home').then((m) => m.Home) },
  { path: 'pay', loadComponent: () => import('./pay/pay').then((m) => m.Pay) },
  { path: 'investigator', loadComponent: () => import('./investigator/investigator').then((m) => m.Investigator) },
  { path: '**', redirectTo: '' },
];

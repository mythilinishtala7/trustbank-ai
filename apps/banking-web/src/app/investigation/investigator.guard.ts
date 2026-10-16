import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { InvestigatorSession } from './investigator-session';

export const investigatorGuard: CanActivateFn = (_route, state) => {
  const session = inject(InvestigatorSession);
  if (session.token()) return true;
  return inject(Router).createUrlTree(['/investigation'], { queryParams: { returnUrl: state.url } });
};

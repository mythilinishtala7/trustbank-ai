import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SessionService } from './session.service';

export const customerGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  return session.role() === 'customer' ? true : inject(Router).createUrlTree(['/enter']);
};

/** The entry screen is only for signed-out visitors. */
export const entryGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  return session.role() === 'customer' ? inject(Router).createUrlTree(['/']) : true;
};

import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { tap } from 'rxjs';
import { SessionService } from './session.service';

// Allow-list of customer endpoints: investigation and auth endpoints never get the customer token.
const CUSTOMER_CALL = /^\/api\/v1\/(me|recipients|payments)(\/|\?|$)/;

export function isCustomerCall(url: string): boolean {
  return CUSTOMER_CALL.test(url);
}

export const customerAuthInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isCustomerCall(req.url)) return next(req);
  const session = inject(SessionService);
  const token = session.token();
  const authed = token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;
  return next(authed).pipe(
    tap({
      error: (e) => {
        if (e instanceof HttpErrorResponse && e.status === 401 && session.signedIn()) session.expire();
      },
    }),
  );
};

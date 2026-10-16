import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { customerGuard, entryGuard } from './guards';
import { SessionService } from './session.service';

function run(guard: typeof customerGuard) {
  return TestBed.runInInjectionContext(() => guard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot));
}

describe('guards', () => {
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
  });

  it('customerGuard redirects signed-out visitors to /enter', () => {
    const result = run(customerGuard) as UrlTree;
    expect(TestBed.inject(Router).serializeUrl(result)).toBe('/enter');
  });

  it('customerGuard allows a signed-in customer; entryGuard then redirects home', () => {
    TestBed.inject(SessionService).start({ token: 't', role: 'customer', expiresAt: '2999-01-01T00:00:00Z', displayName: 'A' });
    expect(run(customerGuard)).toBe(true);
    expect(TestBed.inject(Router).serializeUrl(run(entryGuard) as UrlTree)).toBe('/');
  });

  it('entryGuard allows signed-out visitors', () => {
    expect(run(entryGuard)).toBe(true);
  });
});

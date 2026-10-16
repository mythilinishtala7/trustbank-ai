import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { SESSION_KEY, SessionService } from './session.service';

const auth = { token: 'tok', role: 'customer' as const, expiresAt: '2999-01-01T00:00:00Z', displayName: 'Asha Menon' };

describe('SessionService', () => {
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
  });

  it('stores token, role and display name in sessionStorage', () => {
    const s = TestBed.inject(SessionService);
    expect(s.signedIn()).toBe(false);
    s.start(auth);
    expect(s.token()).toBe('tok');
    expect(s.role()).toBe('customer');
    expect(s.displayName()).toBe('Asha Menon');
    expect(JSON.parse(sessionStorage.getItem(SESSION_KEY)!).token).toBe('tok');
  });

  it('restores a stored session but ignores an expired one', () => {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ ...auth, expiresAt: '2000-01-01T00:00:00Z' }));
    expect(TestBed.inject(SessionService).signedIn()).toBe(false);
  });

  it('clears on expire and returns to the entry screen', async () => {
    const s = TestBed.inject(SessionService);
    const router = TestBed.inject(Router);
    const nav = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    s.start(auth);
    s.expire();
    expect(s.signedIn()).toBe(false);
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
    expect(nav).toHaveBeenCalledWith('/enter');
  });
});

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { Gate } from './gate';
import { InvestigationApi, InvestigationApiError } from './investigation.api';
import { INVESTIGATOR_STORAGE_KEY, InvestigatorSession } from './investigator-session';
import { investigatorGuard } from './investigator.guard';

@Component({ template: '' })
class Stub {}

const CODE = 'demo-access-code';

function setup() {
  sessionStorage.clear();
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([(req, next) => next(req.clone({ headers: req.headers.set('Authorization', 'Bearer CUSTOMER') }))])),
      provideHttpClientTesting(),
      provideRouter([
        { path: 'investigation', component: Stub },
        { path: 'investigation/transactions/:id', component: Stub },
      ]),
    ],
  });
  return { http: TestBed.inject(HttpTestingController), session: TestBed.inject(InvestigatorSession), api: TestBed.inject(InvestigationApi), router: TestBed.inject(Router) };
}

function signIn(session: InvestigatorSession) {
  session.signIn('inv-token', new Date(Date.now() + 3600_000).toISOString());
}

describe('Gate', () => {
  function render() {
    const ctx = setup();
    const fixture = TestBed.createComponent(Gate);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    const input = el.querySelector<HTMLInputElement>('input')!;
    const submit = (code: string) => {
      input.value = code;
      el.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }));
      fixture.detectChanges();
    };
    return { ...ctx, fixture, el, input, submit };
  }

  it('is a password field with a label and never stores or keeps the code', () => {
    const { el, input, submit, http, session } = render();
    expect(input.type).toBe('password');
    expect(el.querySelector('label[for="inv-code"]')).toBeTruthy();
    submit(CODE);
    const req = http.expectOne('/api/v1/auth/investigator');
    expect(req.request.body).toEqual({ code: CODE });
    expect(input.value).toBe('');
    req.flush({ token: 'tok', role: 'investigator', expiresAt: new Date(Date.now() + 60_000).toISOString() });
    expect(session.token()).toBe('tok');
    expect(sessionStorage.getItem(INVESTIGATOR_STORAGE_KEY)).not.toContain(CODE);
    expect(JSON.stringify(Object.entries(sessionStorage))).not.toContain(CODE);
  });

  it('shows a generic message for a wrong code', () => {
    const { el, submit, http, fixture, session } = render();
    submit('wrong');
    http.expectOne('/api/v1/auth/investigator').flush({ error: { code: 'UNAUTHENTICATED', message: 'Invalid code', requestId: 'r' } }, { status: 401, statusText: 'Unauthorized' });
    fixture.detectChanges();
    expect(el.querySelector('[role="alert"]')!.textContent).toContain('not accepted');
    expect(session.authenticated()).toBe(false);
  });

  it('shows try-later on 429', () => {
    const { el, submit, http, fixture } = render();
    submit('x');
    http.expectOne('/api/v1/auth/investigator').flush({ error: { code: 'RATE_LIMITED', message: 'slow down', requestId: 'r' } }, { status: 429, statusText: 'Too Many' });
    fixture.detectChanges();
    expect(el.textContent).toMatch(/try again later/i);
  });

  it('does not call the API for an empty code', () => {
    const { submit, http, el, fixture } = render();
    submit('  ');
    http.expectNone('/api/v1/auth/investigator');
    fixture.detectChanges();
    expect(el.textContent).toContain('Enter the access code');
  });
});

describe('investigatorGuard', () => {
  const run = (url: string) => TestBed.runInInjectionContext(() => investigatorGuard({} as ActivatedRouteSnapshot, { url } as RouterStateSnapshot));

  it('redirects to the gate (with returnUrl) when there is no token', () => {
    setup();
    const result = run('/investigation/transactions/txn_1') as UrlTree;
    expect(TestBed.inject(Router).serializeUrl(result)).toBe('/investigation?returnUrl=%2Finvestigation%2Ftransactions%2Ftxn_1');
  });

  it('allows a valid token', () => {
    const { session } = setup();
    signIn(session);
    expect(run('/investigation/transactions/txn_1')).toBe(true);
  });

  it('rejects and clears an expired token', () => {
    const { session } = setup();
    session.signIn('old', new Date(Date.now() - 1000).toISOString());
    expect(run('/investigation/transactions/txn_1')).toBeInstanceOf(UrlTree);
    expect(sessionStorage.getItem(INVESTIGATOR_STORAGE_KEY)).toBeNull();
  });
});

describe('InvestigationApi', () => {
  it('attaches the investigator token itself, not the customer interceptor token', () => {
    const { http, session, api } = setup();
    signIn(session);
    api.recent().subscribe();
    const req = http.expectOne('/api/v1/investigation/transactions?limit=20');
    expect(req.request.headers.get('Authorization')).toBe('Bearer inv-token');
    req.flush([]);
  });

  it('401 clears the token and returns to the gate', () => {
    const { http, session, api, router } = setup();
    signIn(session);
    const nav = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    let error: InvestigationApiError | undefined;
    api.transaction('txn_1').subscribe({ error: (e) => (error = e) });
    http.expectOne('/api/v1/investigation/transactions/txn_1').flush({ error: { code: 'UNAUTHENTICATED', message: 'expired', requestId: 'r' } }, { status: 401, statusText: 'Unauthorized' });
    expect(error?.status).toBe(401);
    expect(session.authenticated()).toBe(false);
    expect(session.notice()).not.toBe('');
    expect(nav).toHaveBeenCalledWith(['/investigation'], expect.anything());
  });

  it('403 keeps a clear error and does not sign out', () => {
    const { http, session, api } = setup();
    signIn(session);
    let error: InvestigationApiError | undefined;
    api.transaction('txn_1').subscribe({ error: (e) => (error = e) });
    http.expectOne('/api/v1/investigation/transactions/txn_1').flush({ error: { code: 'FORBIDDEN', message: 'no', requestId: 'r' } }, { status: 403, statusText: 'Forbidden' });
    expect(error).toMatchObject({ status: 403, code: 'FORBIDDEN' });
    expect(session.authenticated()).toBe(true);
  });

  it('url-encodes ids and sends no request without a token', () => {
    const { http, session, api, router } = setup();
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    let status = 0;
    api.transaction('a/b').subscribe({ error: (e: InvestigationApiError) => (status = e.status) });
    http.expectNone(() => true);
    expect(status).toBe(401);
    signIn(session);
    api.timeline('a/b', 4).subscribe();
    http.expectOne('/api/v1/investigation/transactions/a%2Fb/timeline?after=4').flush({});
  });
});

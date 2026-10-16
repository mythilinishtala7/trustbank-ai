import { HttpErrorResponse, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { ApiService, NETWORK_MESSAGE, UNAVAILABLE_MESSAGE, normalizeError } from './api.service';
import { customerAuthInterceptor } from './auth.interceptor';
import type { ApiError } from './models';
import { SessionService } from './session.service';
import { payment } from '../testing/fixtures';

describe('normalizeError', () => {
  it('parses the contract error envelope', () => {
    const e = normalizeError(new HttpErrorResponse({ status: 422, error: { error: { code: 'VALIDATION_ERROR', message: 'Bad amount', requestId: 'req_1' } } }));
    expect(e).toMatchObject({ kind: 'validation', code: 'VALIDATION_ERROR', message: 'Bad amount', requestId: 'req_1' });
  });

  it('turns 503 / UNAVAILABLE into a friendly state', () => {
    const e = normalizeError(new HttpErrorResponse({ status: 503, error: { error: { code: 'UNAVAILABLE', message: 'neo4j down', requestId: 'r' } } }));
    expect(e.kind).toBe('unavailable');
    expect(e.message).toBe(UNAVAILABLE_MESSAGE);
  });

  it('turns status 0 into cannot-reach-server', () => {
    const e = normalizeError(new HttpErrorResponse({ status: 0, error: new ProgressEvent('error') }));
    expect(e).toMatchObject({ kind: 'network', message: NETWORK_MESSAGE });
  });

  it('maps statuses and tolerates non-JSON bodies', () => {
    expect(normalizeError(new HttpErrorResponse({ status: 409, error: { error: { code: 'INVALID_TRANSITION', message: 'm', requestId: 'r' } } })).kind).toBe('conflict');
    expect(normalizeError(new HttpErrorResponse({ status: 404, error: 'Not Found' })).kind).toBe('notFound');
    expect(normalizeError(new HttpErrorResponse({ status: 500, error: '<html>' })).message).toMatch(/something went wrong/i);
  });
});

describe('ApiService + customer interceptor', () => {
  let http: HttpTestingController;
  let api: ApiService;
  let session: SessionService;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(withInterceptors([customerAuthInterceptor])), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    api = TestBed.inject(ApiService);
    session = TestBed.inject(SessionService);
    session.start({ token: 'cust-token', role: 'customer', expiresAt: '2999-01-01T00:00:00Z', displayName: 'A' });
  });

  afterEach(() => http.verify());

  it('sends the Idempotency-Key and Bearer token on POST /payments', () => {
    api.createPayment({ recipient: 'a@b', amount: 5 }, 'key-1').subscribe();
    const req = http.expectOne('/api/v1/payments');
    expect(req.request.headers.get('Idempotency-Key')).toBe('key-1');
    expect(req.request.headers.get('Authorization')).toBe('Bearer cust-token');
    req.flush(payment());
  });

  it('never attaches the customer token to investigation or auth calls', () => {
    const raw = TestBed.inject(HttpClient);
    raw.get('/api/v1/investigation/transactions').subscribe();
    raw.post('/api/v1/auth/investigator', { code: 'x' }).subscribe();
    api.personas().subscribe();
    for (const r of http.match(() => true)) {
      expect(r.request.headers.has('Authorization')).toBe(false);
      r.flush([]);
    }
  });

  it('clears the session and goes to /enter on 401', () => {
    const nav = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    let err: ApiError | undefined;
    api.me().subscribe({ error: (e: ApiError) => (err = e) });
    http.expectOne('/api/v1/me').flush({ error: { code: 'UNAUTHENTICATED', message: 'no', requestId: 'r' } }, { status: 401, statusText: 'Unauthorized' });
    expect(err?.kind).toBe('unauthenticated');
    expect(session.signedIn()).toBe(false);
    expect(nav).toHaveBeenCalledWith('/enter');
  });

  it('posts the action endpoints with empty bodies and the PIN only to authorize', () => {
    api.acknowledge('txn_1').subscribe();
    expect(http.expectOne('/api/v1/payments/txn_1/acknowledge').request.body).toEqual({});
    api.authorize('txn_2', '1234').subscribe();
    expect(http.expectOne('/api/v1/payments/txn_2/authorize').request.body).toEqual({ pin: '1234' });
    http.match(() => true).forEach((r) => r.flush(payment()));
  });
});

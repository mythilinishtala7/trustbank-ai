import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, TestRequest, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { CYTOSCAPE_OPTIONS } from './graph-view';
import { InvestigationShell } from './investigation-shell';
import { INVESTIGATION_ROUTES } from './investigation.routes';
import { INVESTIGATOR_STORAGE_KEY, InvestigatorSession } from './investigator-session';
import { Landing } from './landing';
import { HISTORICAL, NOVATRADE, SHOPKEEPER, TIMELINE_EVENTS, timelineResponse } from './testing/fixtures';
import { FEED_TIMING, STREAM_FETCH } from './timeline-feed';

const BASE = '/api/v1/investigation/transactions';
const err = (status: number, code: string) => ({ status, statusText: code, body: { error: { code, message: code, requestId: 'r' } } });

function setup() {
  sessionStorage.clear();
  const streamFetch = vi.fn(async () => new Response('', { status: 500 }));
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([{ path: 'investigation', children: INVESTIGATION_ROUTES }]),
      { provide: CYTOSCAPE_OPTIONS, useValue: { headless: true } },
      { provide: STREAM_FETCH, useValue: streamFetch },
      { provide: FEED_TIMING, useValue: { pollMs: 5, idleMs: 5 } },
    ],
  });
  const session = TestBed.inject(InvestigatorSession);
  session.signIn('inv-token', new Date(Date.now() + 3600_000).toISOString());
  return { http: TestBed.inject(HttpTestingController), session, streamFetch };
}

function flush(req: TestRequest, body: object | null, failure?: ReturnType<typeof err>) {
  if (failure) req.flush(failure.body, { status: failure.status, statusText: failure.statusText });
  else req.flush(body);
}

async function openTransaction(id: string) {
  const ctx = setup();
  const harness = await RouterTestingHarness.create();
  const nav = harness.navigateByUrl(`/investigation/transactions/${id}`);
  return { ...ctx, harness, nav };
}

describe('TransactionPage', () => {
  it('shows a clear not-found state for an unknown id (404)', async () => {
    const { http, nav, harness } = await openTransaction('txn_nope');
    await nav;
    harness.detectChanges();
    flush(http.expectOne(`${BASE}/txn_nope`), null, err(404, 'NOT_FOUND'));
    harness.detectChanges();
    const el: HTMLElement = harness.routeNativeElement!;
    expect(el.querySelector('[data-testid="not-found"]')!.textContent).toContain('txn_nope');
    expect(el.querySelector('inv-graph')).toBeNull();
    http.verify();
  });

  it('shows a retryable unavailable state on 503', async () => {
    const { http, nav, harness } = await openTransaction('txn_1');
    await nav;
    harness.detectChanges();
    flush(http.expectOne(`${BASE}/txn_1`), null, err(503, 'UNAVAILABLE'));
    harness.detectChanges();
    const el = harness.routeNativeElement!;
    expect(el.querySelector('[data-testid="unavailable"]')).toBeTruthy();
    el.querySelector<HTMLButtonElement>('[data-testid="unavailable"] button')!.click();
    harness.detectChanges();
    http.expectOne(`${BASE}/txn_1`);
  });

  it('shows a clear message on 403 without signing out', async () => {
    const { http, nav, harness, session } = await openTransaction('txn_1');
    await nav;
    harness.detectChanges();
    flush(http.expectOne(`${BASE}/txn_1`), null, err(403, 'FORBIDDEN'));
    harness.detectChanges();
    expect(harness.routeNativeElement!.querySelector('[data-testid="forbidden"]')).toBeTruthy();
    expect(session.authenticated()).toBe(true);
  });

  it('401 clears the token and returns to the gate', async () => {
    const { http, nav, harness, session } = await openTransaction('txn_1');
    await nav;
    harness.detectChanges();
    flush(http.expectOne(`${BASE}/txn_1`), null, err(401, 'UNAUTHENTICATED'));
    await vi.waitFor(() => expect(TestBed.inject(Router).url).toContain('/investigation?returnUrl'));
    expect(session.authenticated()).toBe(false);
    expect(sessionStorage.getItem(INVESTIGATOR_STORAGE_KEY)).toBeNull();
  });

  it('renders summary, graph, evidence and timeline from one bounded call (never loads the whole network)', async () => {
    const { http, nav, harness } = await openTransaction('txn_nova0001');
    await nav;
    harness.detectChanges();
    flush(http.expectOne(`${BASE}/txn_nova0001`), NOVATRADE);
    harness.detectChanges();
    const timeline = http.expectOne(`${BASE}/txn_nova0001/timeline?after=0`);
    timeline.flush(timelineResponse(TIMELINE_EVENTS, 'HOLD_ACTIVE', true));
    await vi.waitFor(() => expect(harness.routeNativeElement!.querySelectorAll('.ev').length).toBe(5));
    harness.detectChanges();

    const el = harness.routeNativeElement!;
    expect(el.textContent).toContain('Nova Trade Desk');
    expect(el.textContent).toContain('₹25,000');
    expect(el.textContent).toContain('Simulated demo data');
    expect(el.querySelector('inv-graph')).toBeTruthy();
    expect(el.textContent).toContain('network.layering');
    expect(el.querySelectorAll('.entity-list ul[aria-label="Nodes"] li')).toHaveLength(NOVATRADE.graph.nodes.length);
    expect(el.querySelector('[data-testid="truncated"]')).toBeTruthy();

    // No other request: no list-all-nodes / network / graph endpoint is ever called.
    http.verify();
  });

  it('historical transactions skip the timeline and show the no-assessment state', async () => {
    const { http, nav, harness, streamFetch } = await openTransaction('txn_hist_1');
    await nav;
    harness.detectChanges();
    flush(http.expectOne(`${BASE}/txn_hist_1`), HISTORICAL);
    harness.detectChanges();
    const el = harness.routeNativeElement!;
    expect(el.textContent).toContain('no stored assessments');
    expect(el.textContent).toContain('no execution trace');
    http.verify();
    expect(streamFetch).not.toHaveBeenCalled();
  });

  it('shopkeeper payment: no suspicious evidence, ordinary context', async () => {
    const { http, nav, harness } = await openTransaction('txn_shop0001');
    await nav;
    harness.detectChanges();
    flush(http.expectOne(`${BASE}/txn_shop0001`), SHOPKEEPER);
    harness.detectChanges();
    http.expectOne(`${BASE}/txn_shop0001/timeline?after=0`).flush(timelineResponse([], 'READY_FOR_AUTH', true, 'txn_shop0001'));
    harness.detectChanges();
    const el = harness.routeNativeElement!;
    expect(el.querySelector('[data-testid="no-suspicious"]')).toBeTruthy();
    expect(el.textContent).toContain('long_dwell');
  });
});

describe('Landing and shell', () => {
  it('shows the gate without a token and the search + recent list with one', async () => {
    const { http, session } = setup();
    session.clear();
    const harness = await RouterTestingHarness.create('/investigation');
    harness.detectChanges();
    const el = harness.routeNativeElement!;
    expect(el.querySelector('inv-gate')).toBeTruthy();
    expect(el.querySelector('inv-search-page')).toBeNull();
    http.expectNone(`${BASE}?limit=20`);

    session.signIn('t', new Date(Date.now() + 60_000).toISOString());
    harness.detectChanges();
    const list = http.expectOne(`${BASE}?limit=20`);
    expect(list.request.headers.get('Authorization')).toBe('Bearer t');
    list.flush([{ transactionId: 'txn_ab12cd34', customerName: 'Asha Menon', recipientName: 'Nova Trade Desk', amount: 25000, status: 'HOLD_ACTIVE', createdAt: '2026-10-15T10:00:00Z' }]);
    harness.detectChanges();
    const link = el.querySelector<HTMLAnchorElement>('table a')!;
    expect(link.textContent).toBe('txn_ab12cd34');
    expect(link.getAttribute('href')).toBe('/investigation/transactions/txn_ab12cd34');
    expect(el.textContent).toContain('Simulated demo data');
  });

  it('shows an empty state for no payments and an error with retry', async () => {
    const { http } = setup();
    const harness = await RouterTestingHarness.create('/investigation');
    harness.detectChanges();
    http.expectOne(`${BASE}?limit=20`).flush([]);
    harness.detectChanges();
    expect(harness.routeNativeElement!.textContent).toContain('No payments yet');
  });

  it('shows an error state when the recent list is unavailable', async () => {
    const { http } = setup();
    const harness = await RouterTestingHarness.create('/investigation');
    harness.detectChanges();
    flush(http.expectOne(`${BASE}?limit=20`), null, err(503, 'UNAVAILABLE'));
    harness.detectChanges();
    expect(harness.routeNativeElement!.textContent).toContain('temporarily unavailable');
  });

  it('navigates to the transaction route when an id is submitted', async () => {
    const { http } = setup();
    const harness = await RouterTestingHarness.create('/investigation');
    harness.detectChanges();
    http.expectOne(`${BASE}?limit=20`).flush([]);
    harness.detectChanges();
    const el = harness.routeNativeElement!;
    el.querySelector<HTMLInputElement>('#inv-txn-id')!.value = ' txn_ab12cd34 ';
    el.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await vi.waitFor(() => expect(TestBed.inject(Router).url).toBe('/investigation/transactions/txn_ab12cd34'));
  });

  it('sign out clears the token and returns to the gate', async () => {
    const { http, session } = setup();
    const harness = await RouterTestingHarness.create('/investigation');
    harness.detectChanges();
    http.expectOne(`${BASE}?limit=20`).flush([]);
    const signOut = [...harness.routeNativeElement!.querySelectorAll('button')].find((b) => b.textContent!.trim() === 'Sign out');
    signOut!.click();
    await vi.waitFor(() => expect(session.authenticated()).toBe(false));
    expect(sessionStorage.getItem(INVESTIGATOR_STORAGE_KEY)).toBeNull();
  });
});

describe('route table', () => {
  it('guards the transaction route and exposes the shell + landing', () => {
    const root = INVESTIGATION_ROUTES[0];
    const children = root.children!;
    expect(children.find((c) => c.path === 'transactions/:id')!.canActivate).toHaveLength(1);
    expect(children.find((c) => c.path === '')).toBeTruthy();
    expect(InvestigationShell).toBeTruthy();
    expect(Landing).toBeTruthy();
  });
});

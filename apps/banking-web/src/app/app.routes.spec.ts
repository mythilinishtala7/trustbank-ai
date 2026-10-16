import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from './app.routes';
import { ME } from './testing/fixtures';
import { SessionService } from './core/session.service';

describe('app routes', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter(routes)] });
    http = TestBed.inject(HttpTestingController);
  });

  it('sends a signed-out visitor to the persona entry, with the simulated-demo badge and no console link', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/');
    http.expectOne('/api/v1/personas').flush([]);
    expect(TestBed.inject(Router).url).toBe('/enter');
    harness.fixture.detectChanges();
    const el = harness.routeNativeElement!.ownerDocument.body;
    expect(el.textContent).toContain('Simulated demo · no real money');
    expect(el.querySelector('a[href*="investigation"]')).toBeNull();
  });

  it('shows home for a signed-in customer and keeps them off the entry screen', async () => {
    TestBed.inject(SessionService).start({ token: 't', role: 'customer', expiresAt: '2999-01-01T00:00:00Z', displayName: 'Asha Menon' });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/enter');
    http.expectOne('/api/v1/me').flush(ME);
    expect(TestBed.inject(Router).url).toBe('/');
  });

  it('redirects unknown URLs to the root', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/nope');
    http.expectOne('/api/v1/personas').flush([]);
    expect(TestBed.inject(Router).url).toBe('/enter');
    expect(harness.fixture).toBeTruthy();
  });
});

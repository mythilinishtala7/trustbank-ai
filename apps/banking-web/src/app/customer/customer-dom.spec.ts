import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { ME, STATUS_FIXTURES } from '../testing/fixtures';
import { Home } from './home/home';
import { PayStatus } from './pay/pay-status';

// Internal investigation vocabulary must never reach the customer DOM.
const FORBIDDEN = /\b(scores?|agents?|graph|confidence|thresholds?|evidence|anomal\w*|traces?|investigat\w*|fraudulent|fraud ring|neo4j|gemini)\b/i;

describe('customer DOM whitelist', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([{ path: 'pay/:id', component: PayStatus }, { path: '', component: Home }])],
    });
    http = TestBed.inject(HttpTestingController);
  });

  it('home contains no investigation vocabulary or console link', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/', Home);
    http.expectOne('/api/v1/me').flush(ME);
    harness.fixture.detectChanges();
    const el = harness.fixture.nativeElement as HTMLElement;
    expect(el.textContent).not.toMatch(FORBIDDEN);
    expect(el.querySelector('a[href*="investigat"]')).toBeNull();
  });

  for (const p of STATUS_FIXTURES) {
    it(`${p.status} view contains no investigation vocabulary`, async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/pay/txn_ab12cd34', PayStatus);
      http.expectOne('/api/v1/payments/txn_ab12cd34').flush(p);
      harness.fixture.detectChanges();
      const el = harness.fixture.nativeElement as HTMLElement;
      expect(el.textContent!.length).toBeGreaterThan(20);
      expect(el.textContent).not.toMatch(FORBIDDEN);
      expect(el.querySelector('a[href*="investigat"]')).toBeNull();
    });
  }
});

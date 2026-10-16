import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ME } from '../../testing/fixtures';
import { Home } from './home';

describe('Home', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
  });

  it('shows loading, then balance, Pay action and recent transactions', () => {
    const fixture = TestBed.createComponent(Home);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Loading');
    http.expectOne('/api/v1/me').flush(ME);
    fixture.detectChanges();
    expect(el.textContent).toContain('Asha Menon');
    expect(el.textContent).toContain('125,000');
    expect(el.textContent).toContain('Greenleaf Bakery');
    expect(el.querySelector('a[href="/pay"]')?.textContent).toContain('Pay');
  });

  it('shows an empty state when there are no transactions', () => {
    const fixture = TestBed.createComponent(Home);
    fixture.detectChanges();
    http.expectOne('/api/v1/me').flush({ ...ME, recentTransactions: [] });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('No transactions yet');
  });

  it('shows a friendly 503 state and retries', () => {
    const fixture = TestBed.createComponent(Home);
    fixture.detectChanges();
    http.expectOne('/api/v1/me').flush({ error: { code: 'UNAVAILABLE', message: 'x', requestId: 'r' } }, { status: 503, statusText: 'x' });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toMatch(/temporarily unavailable/i);
    el.querySelector<HTMLButtonElement>('[role=alert] button')!.click();
    http.expectOne('/api/v1/me').flush(ME);
    fixture.detectChanges();
    expect(el.textContent).toContain('Asha Menon');
  });
});

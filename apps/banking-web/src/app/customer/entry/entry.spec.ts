import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { SessionService } from '../../core/session.service';
import { Entry } from './entry';

const PERSONAS = [
  { id: 'cust_asha', displayName: 'Asha Menon', handle: 'asha.menon@trustpay', blurb: 'Regular customer' },
  { id: 'cust_priya', displayName: 'Priya Nair', handle: 'priya.nair@trustpay', blurb: 'Regular customer' },
];

describe('Entry', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
  });

  it('lists personas, says it is a simulated demo with no passwords, and signs in on pick', async () => {
    const fixture = TestBed.createComponent(Entry);
    fixture.detectChanges();
    http.expectOne('/api/v1/personas').flush(PERSONAS);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toMatch(/simulated demo/i);
    expect(el.textContent).toMatch(/no passwords/i);
    const buttons = el.querySelectorAll<HTMLButtonElement>('button.persona');
    expect(buttons.length).toBe(2);

    const nav = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    buttons[1].click();
    const req = http.expectOne('/api/v1/auth/customer');
    expect(req.request.body).toEqual({ personaId: 'cust_priya' });
    req.flush({ token: 't', role: 'customer', expiresAt: '2999-01-01T00:00:00Z', displayName: 'Priya Nair' });
    expect(TestBed.inject(SessionService).displayName()).toBe('Priya Nair');
    expect(nav).toHaveBeenCalledWith('/');
  });

  it('shows the friendly unavailable state with retry', () => {
    const fixture = TestBed.createComponent(Entry);
    fixture.detectChanges();
    http.expectOne('/api/v1/personas').flush({ error: { code: 'UNAVAILABLE', message: 'x', requestId: 'r' } }, { status: 503, statusText: 'Service Unavailable' });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[role=alert]')?.textContent).toMatch(/temporarily unavailable/i);
    el.querySelector<HTMLButtonElement>('[role=alert] button')!.click();
    http.expectOne('/api/v1/personas').flush(PERSONAS);
  });
});

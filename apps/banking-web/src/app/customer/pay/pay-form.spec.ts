import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { payment } from '../../testing/fixtures';
import { PayForm } from './pay-form';

function type(el: HTMLElement, selector: string, value: string): void {
  const input = el.querySelector<HTMLInputElement>(selector)!;
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

describe('PayForm', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<PayForm>;
  let el: HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PayForm);
    el = fixture.nativeElement;
    fixture.detectChanges();
  });

  const submit = () => {
    el.querySelector<HTMLButtonElement>('button[type=submit]')!.click();
    fixture.detectChanges();
  };

  it('blocks invalid recipients without calling the API', () => {
    type(el, '#recipient', '12345');
    fixture.detectChanges();
    submit();
    expect(el.querySelector('#recipient-error')?.textContent).toMatch(/9 to 18 digits/);
    http.expectNone((r) => r.url.includes('/recipients/lookup'));
  });

  it('has no demo scenario shortcuts', () => {
    expect(el.querySelectorAll('.chip').length).toBe(0);
    expect(el.textContent).not.toMatch(/scenario/i);
  });

  it('shows an unknown recipient as unverified, never fraudulent', () => {
    type(el, '#recipient', 'stranger@somebank');
    fixture.detectChanges();
    submit();
    const req = http.expectOne((r) => r.url === '/api/v1/recipients/lookup');
    expect(req.request.params.get('q')).toBe('stranger@somebank');
    req.flush({ found: false, verified: false, displayName: null, handle: 'stranger@somebank', maskedAccount: null });
    fixture.detectChanges();
    expect(el.textContent).toContain('Unverified recipient');
    expect(el.textContent).not.toMatch(/fraud/i);
  });

  it('walks recipient -> amount -> review, then creates the payment with one idempotency key reused on retry', () => {
    type(el, '#recipient', 'rahul.verma@trustpay');
    fixture.detectChanges();
    submit();
    http.expectOne((r) => r.url === '/api/v1/recipients/lookup').flush({ found: true, verified: true, displayName: 'Rahul Verma', handle: 'rahul.verma@trustpay', maskedAccount: 'XXXX1234' });
    fixture.detectChanges();
    expect(el.textContent).toContain('Verified recipient');
    submit(); // Continue

    expect(el.querySelector('h1')?.textContent).toContain('How much');
    submit();
    expect(el.querySelector('#amount-error')?.textContent).toMatch(/Enter an amount/);
    type(el, '#amount', '2500');
    type(el, '#note', 'Dinner');
    fixture.detectChanges();
    expect(el.textContent).toContain('6/80');
    submit();

    expect(el.querySelector('h1')?.textContent).toContain('Review payment');
    el.querySelector<HTMLButtonElement>('.btn:not(.secondary)')!.click();
    fixture.detectChanges();
    const first = http.expectOne('/api/v1/payments');
    expect(first.request.body).toEqual({ recipient: 'rahul.verma@trustpay', amount: 2500, note: 'Dinner' });
    const key = first.request.headers.get('Idempotency-Key');
    expect(key).toBeTruthy();
    expect(el.textContent).toContain('Checking payment…');
    first.flush({ error: { code: 'UNAVAILABLE', message: 'x', requestId: 'r' } }, { status: 503, statusText: 'x' });
    fixture.detectChanges();
    expect(el.textContent).toMatch(/temporarily unavailable/i);

    const nav = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    el.querySelector<HTMLButtonElement>('[role=alert] button')!.click();
    const retry = http.expectOne('/api/v1/payments');
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    retry.flush(payment({ status: 'READY_FOR_AUTH' }));
    expect(nav).toHaveBeenCalledWith(['/pay', 'txn_ab12cd34'], { state: { payment: expect.objectContaining({ id: 'txn_ab12cd34' }) } });
  });
});

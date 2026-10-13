import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Pay } from './pay';
import type { Payment } from '../models';

const base = {
  id: 'pay_1',
  beneficiary: { id: 'b', displayName: 'Nova Trade Desk', handle: 'nova.trade@trustpay', maskedAccount: 'X', bankLabel: 'Demo Bank', complaintCount: 0 },
  amount: 25000,
  note: '',
  assessment: { score: 55, level: 'MEDIUM', signals: [], recommendedAction: 'REVIEW', beneficiaryId: 'b', graphEntityIds: [], explanation: '', holdSeconds: 0 },
  initialAssessment: {},
  questions: [],
  explanation: { headline: 'Please double-check', summary: 's', signalIds: [], provider: 'mock' },
  createdAt: '',
  trace: [],
  simulated: true,
} as unknown as Payment;

describe('Pay', () => {
  it('shows scam check, never the PIN step, until the server allows it', async () => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(Pay);
    fixture.detectChanges();
    http.expectOne('/api/scenarios').flush([]);
    const c = fixture.componentInstance;
    c.recipient.set('nova.trade@trustpay');
    c.amount.set(25000);
    c.submit();
    http.expectOne('/api/payments').flush({
      ...base,
      status: 'SCAM_CHECK',
      questions: [{ id: 'promisedBenefit', text: 'Were you promised returns?', options: [{ value: 'YES', label: 'Yes' }] }],
    });
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Quick safety check');
    expect(el.querySelector('#pin')).toBeNull();
  });

  it('locks the PIN step during a hold', async () => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(Pay);
    fixture.detectChanges();
    http.expectOne('/api/scenarios').flush([]);
    const c = fixture.componentInstance;
    c.recipient.set('nova.trade@trustpay');
    c.amount.set(25000);
    c.submit();
    http.expectOne('/api/payments').flush({ ...base, status: 'HOLD', holdUntil: new Date(Date.now() + 120_000).toISOString() });
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.countdown')?.textContent).toContain('2:00');
    expect(el.querySelector('#pin')).toBeNull();
    c.ngOnDestroy();
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import type { CustomerPayment } from '../../core/models';
import { NOW, QUESTIONS, STATUS_FIXTURES, payment } from '../../testing/fixtures';
import { PayStatus } from './pay-status';

const URL = '/api/v1/payments/txn_ab12cd34';

describe('PayStatus', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<unknown>;
  let el: HTMLElement;

  async function mount(p: CustomerPayment): Promise<void> {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/pay/txn_ab12cd34', PayStatus);
    http.expectOne(URL).flush(p);
    fixture = harness.fixture;
    fixture.detectChanges();
    el = fixture.nativeElement;
  }

  const flush = (p: CustomerPayment, suffix = '') => {
    http.expectOne(URL + suffix).flush(p);
    fixture.detectChanges();
  };
  const button = (re: RegExp) => [...el.querySelectorAll('button, a.btn')].find((b) => re.test(b.textContent ?? '')) as HTMLButtonElement | undefined;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([{ path: 'pay/:id', component: PayStatus }])],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    vi.useRealTimers();
    http.verify();
  });

  it('QUESTIONNAIRE renders at most 3 questions with radios and a 300-char free-text limit, then submits answers', async () => {
    await mount(payment({ status: 'QUESTIONNAIRE', questions: QUESTIONS, actions: ['ANSWER', 'CANCEL'] }));
    expect(el.querySelectorAll('fieldset').length).toBe(3);
    expect(el.textContent).not.toContain('Fourth question');
    expect(el.querySelectorAll('input[type=radio]').length).toBe(6);
    const ta = el.querySelectorAll('textarea');
    expect(ta.length).toBe(1);
    expect(ta[0].maxLength).toBe(300);

    const submit = button(/^Continue$/)!;
    expect(submit.disabled).toBe(true);
    ta[0].value = 'x'.repeat(350);
    ta[0].dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(el.textContent).toContain('300/300');

    for (const fs of Array.from(el.querySelectorAll('fieldset'))) {
      const radio = fs.querySelector<HTMLInputElement>('input[type=radio]')!;
      radio.checked = true;
      radio.dispatchEvent(new Event('change'));
    }
    fixture.detectChanges();
    expect(submit.disabled).toBe(false);
    submit.click();
    const req = http.expectOne(URL + '/answers');
    expect(req.request.body.answers).toHaveLength(3);
    expect(req.request.body.answers[0]).toMatchObject({ questionId: 'source_of_details', option: 'friend_family' });
    expect(req.request.body.answers[0].freeText).toHaveLength(300);
    expect(req.request.body.answers[1].freeText).toBeUndefined();
    req.flush(payment({ status: 'READY_FOR_AUTH' }));
    fixture.detectChanges();
    expect(el.querySelector('#pin')).not.toBeNull();
  });

  it('REVIEW requires an explicit acknowledgement before it calls /acknowledge', async () => {
    await mount(STATUS_FIXTURES.find((p) => p.status === 'REVIEW')!);
    expect(el.textContent).toContain('First payment to this recipient');
    expect(el.querySelector('#pin')).toBeNull();
    const cont = button(/^Continue$/)!;
    expect(cont.disabled).toBe(true);
    cont.click();
    http.expectNone(URL + '/acknowledge');

    const box = el.querySelector<HTMLInputElement>('input[type=checkbox]')!;
    box.checked = true;
    box.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(cont.disabled).toBe(false);
    cont.click();
    http.expectOne(URL + '/acknowledge').flush(payment({ status: 'READY_FOR_AUTH' }));
    fixture.detectChanges();
    expect(el.querySelector('#pin')).not.toBeNull();
  });

  it('HOLD_ACTIVE shows reference, countdown, guidance and Cancel, with no path to the PIN', async () => {
    await mount(STATUS_FIXTURES.find((p) => p.status === 'HOLD_ACTIVE')!);
    expect(el.querySelector('.countdown')?.textContent).toContain('3:00');
    expect(el.textContent).toContain('txn_ab12cd34');
    expect(el.textContent).toMatch(/independently/i);
    expect(button(/Cancel payment/)).toBeDefined();
    expect(el.querySelector('#pin')).toBeNull();
    expect(button(/Authorize|Continue|verified/i)).toBeUndefined();
    expect(el.querySelector('input[type=password]')).toBeNull();
  });

  it('counts down from server time (not the client clock), then refetches and shows HOLD_EXPIRED without advancing', async () => {
    vi.useFakeTimers();
    // client clock is an hour ahead of the server; the countdown must still use the server offset
    vi.setSystemTime(NOW + 3_600_000);
    const hold = payment({ status: 'HOLD_ACTIVE', actions: ['CANCEL'], holdUntil: new Date(NOW + 3000).toISOString(), explanation: 'Paused.' });
    await mount(hold);
    expect(el.querySelector('.countdown')?.textContent).toContain('0:03');

    await vi.advanceTimersByTimeAsync(1100);
    fixture.detectChanges();
    expect(el.querySelector('.countdown')?.textContent).toContain('0:02');

    await vi.advanceTimersByTimeAsync(2100);
    fixture.detectChanges();
    expect(el.querySelector('.countdown')?.textContent).toContain('0:00');
    expect(el.querySelector('#pin')).toBeNull();

    flush(payment({ status: 'HOLD_EXPIRED', actions: ['VERIFY', 'CANCEL'], explanation: 'Paused.', holdUntil: hold.holdUntil }));
    expect(el.querySelector('h1')?.textContent).toContain('The pause has ended');
    expect(button(/verified the recipient independently/)).toBeDefined();
    expect(button(/^Continue$/)).toBeUndefined();
    expect(el.querySelector('#pin')).toBeNull();
  });

  it('HOLD_EXPIRED: verify, then Continue, then PIN — only on explicit actions', async () => {
    await mount(STATUS_FIXTURES.find((p) => p.status === 'HOLD_EXPIRED')!);
    button(/verified the recipient independently/)!.click();
    http.expectOne(URL + '/verify').flush(payment({ status: 'HOLD_EXPIRED', verified: true, actions: ['CONTINUE', 'CANCEL'] }));
    fixture.detectChanges();
    expect(button(/verified the recipient independently/)).toBeUndefined();
    expect(el.querySelector('#pin')).toBeNull();
    button(/^Continue$/)!.click();
    http.expectOne(URL + '/continue').flush(payment({ status: 'READY_FOR_AUTH' }));
    fixture.detectChanges();
    expect(el.querySelector('#pin')).not.toBeNull();
  });

  it('READY_FOR_AUTH shows a demo PIN input, validates 4-6 digits, clears the PIN, and shows a simulated receipt', async () => {
    await mount(payment({ status: 'READY_FOR_AUTH' }));
    const pin = el.querySelector<HTMLInputElement>('#pin')!;
    expect(pin.type).toBe('password');
    expect(el.textContent).toMatch(/demo PIN/i);
    pin.value = '12a3';
    pin.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(pin.value).toBe('123');
    button(/Authorize payment/)!.click();
    fixture.detectChanges();
    http.expectNone(URL + '/authorize');
    expect(el.querySelector('#pin-error')?.textContent).toMatch(/4 to 6 digits/);

    pin.value = '1234';
    pin.dispatchEvent(new Event('input'));
    button(/Authorize payment/)!.click();
    fixture.detectChanges();
    expect(pin.value).toBe('');
    http.expectOne(URL + '/authorize').flush(payment({ status: 'COMPLETED', actions: [] }));
    fixture.detectChanges();
    expect(el.textContent).toMatch(/Simulated payment/);
    expect(el.textContent).toContain('txn_ab12cd34');
    expect(el.textContent).toMatch(/not enforced by a real bank/);
  });

  it('renders CANCELLED with no actions', async () => {
    await mount(payment({ status: 'CANCELLED', actions: [] }));
    expect(el.textContent).toContain('cancelled');
    expect(el.querySelector('#pin')).toBeNull();
  });

  it('polls GET while ASSESSING until the status changes', async () => {
    vi.useFakeTimers();
    await mount(payment({ status: 'ASSESSING', actions: ['CANCEL'] }));
    expect(el.textContent).toContain('Checking payment…');
    await vi.advanceTimersByTimeAsync(1500);
    flush(payment({ status: 'ASSESSING', actions: ['CANCEL'] }));
    await vi.advanceTimersByTimeAsync(1500);
    flush(payment({ status: 'READY_FOR_AUTH' }));
    expect(el.querySelector('#pin')).not.toBeNull();
    await vi.advanceTimersByTimeAsync(5000);
  });

  it('shows the friendly service-unavailable state when loading fails with 503', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/pay/txn_ab12cd34', PayStatus);
    http.expectOne(URL).flush({ error: { code: 'UNAVAILABLE', message: 'x', requestId: 'r' } }, { status: 503, statusText: 'x' });
    harness.fixture.detectChanges();
    const text = (harness.fixture.nativeElement as HTMLElement).textContent;
    expect(text).toMatch(/temporarily unavailable/i);
  });

  it('refetches after a conflicting action response', async () => {
    await mount(payment({ status: 'REVIEW', actions: ['ACKNOWLEDGE', 'CANCEL'] }));
    button(/Cancel payment/)!.click();
    http.expectOne(URL + '/cancel').flush({ error: { code: 'INVALID_TRANSITION', message: 'Not allowed now', requestId: 'r' } }, { status: 409, statusText: 'Conflict' });
    fixture.detectChanges();
    expect(el.textContent).toContain('Not allowed now');
    flush(payment({ status: 'CANCELLED', actions: [] }));
    expect(el.textContent).toContain('cancelled');
  });
});

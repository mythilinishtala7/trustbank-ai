import { describe, expect, it } from 'vitest';
import { MockAgentProvider } from '../../agents/src/index';
import { buildGraph, networkFacts } from './graph';
import { ApiError, PaymentService, resolveBeneficiary } from './payments';
import { assess, DEFAULT_CONFIG } from './risk-engine';
import { CUSTOMER_ID, createSeededStore } from './store';

function setup() {
  const time = { now: new Date('2026-10-13T12:00:00Z').getTime() };
  const store = createSeededStore(() => new Date(time.now));
  const service = new PaymentService(store, new MockAgentProvider(), { ...DEFAULT_CONFIG, holdSeconds: 120 });
  return { store, service, time };
}

const score = (recipient: string, amount: number, answers?: Parameters<typeof assess>[0]['answers']) => {
  const { store } = setup();
  return assess({ store, customerId: CUSTOMER_ID, beneficiary: resolveBeneficiary(store, recipient), amount, answers });
};

describe('risk engine scenarios', () => {
  it('A: routine rent is LOW / PROCEED', () => {
    const a = score('rahul.verma@trustpay', 2500);
    expect(a.level).toBe('LOW');
    expect(a.recommendedAction).toBe('PROCEED');
    expect(a.signals).toHaveLength(0);
  });

  it('B: new linked recipient is MEDIUM / REVIEW without claiming complaints', () => {
    const a = score('nova.trade@trustpay', 25000);
    expect(a.level).toBe('MEDIUM');
    expect(a.recommendedAction).toBe('REVIEW');
    expect(a.signals.map((s) => s.id)).toContain('network.flagged_links');
    expect(a.signals.map((s) => s.id)).not.toContain('beneficiary.complaints');
    expect(a.explanation).not.toMatch(/complaint/i);
  });

  it('B with benign answers stays REVIEW', () => {
    const a = score('nova.trade@trustpay', 25000, { sourceOfDetails: 'FRIEND_FAMILY', promisedBenefit: 'NO' });
    expect(a.recommendedAction).toBe('REVIEW');
  });

  it('C: Telegram + promised payouts is HIGH / HOLD', () => {
    const a = score('nova.trade@trustpay', 25000, { sourceOfDetails: 'MESSAGING_APP', promisedBenefit: 'YES' });
    expect(a.level).toBe('HIGH');
    expect(a.recommendedAction).toBe('HOLD');
    expect(a.holdSeconds).toBe(120);
  });

  it('is reproducible', () => {
    expect(score('nova.trade@trustpay', 25000)).toEqual(score('nova.trade@trustpay', 25000));
  });

  it('new beneficiary + unusual amount alone is never HIGH', () => {
    const a = score('fresh.person@trustpay', 90000);
    expect(a.level).not.toBe('HIGH');
    expect(a.score).toBeLessThanOrEqual(DEFAULT_CONFIG.unsupportedCap);
  });

  it('graph and engine share entity ids', () => {
    const { store } = setup();
    const a = assess({ store, customerId: CUSTOMER_ID, beneficiary: store.beneficiaries.get('ben_novatrade')!, amount: 25000 });
    const ids = new Set(buildGraph(store).nodes.map((n) => n.id));
    a.graphEntityIds.forEach((id) => expect(ids.has(id)).toBe(true));
    expect(networkFacts(store, 'ben_novatrade').flaggedNeighborIds).toEqual(['ben_mule_a', 'ben_mule_b']);
  });
});

describe('payment flow', () => {
  it('low risk skips scam check and completes', async () => {
    const { service, store } = setup();
    const p = await service.create({ recipient: 'rahul.verma@trustpay', amount: 2500 });
    expect(p.status).toBe('READY_FOR_AUTH');
    const before = store.customers.get(CUSTOMER_ID)!.balance;
    service.authorize(p.id, '1234');
    expect(store.customers.get(CUSTOMER_ID)!.balance).toBe(before - 2500);
    expect(JSON.stringify(service.get(p.id))).not.toContain('1234');
  });

  it('blocks authorization during scam check, review and hold', async () => {
    const { service, time } = setup();
    const p = await service.create({ recipient: 'nova.trade@trustpay', amount: 25000 });
    expect(p.status).toBe('SCAM_CHECK');
    expect(() => service.authorize(p.id, '1234')).toThrow(ApiError);

    await service.submitAnswers(p.id, { sourceOfDetails: 'MESSAGING_APP', promisedBenefit: 'YES' });
    expect(service.get(p.id).status).toBe('HOLD');
    expect(() => service.authorize(p.id, '1234')).toThrow(ApiError);
    expect(() => service.continue(p.id)).toThrow(/hold still active/);

    time.now += 121_000;
    service.continue(p.id);
    expect(service.get(p.id).status).toBe('READY_FOR_AUTH');
    expect(service.authorize(p.id, '123456').status).toBe('COMPLETED');
  });

  it('review requires acknowledgement; cancel blocks authorization', async () => {
    const { service } = setup();
    const p = await service.create({ recipient: 'nova.trade@trustpay', amount: 25000 });
    await service.submitAnswers(p.id, { sourceOfDetails: 'FRIEND_FAMILY', promisedBenefit: 'NO' });
    expect(service.get(p.id).status).toBe('REVIEW');
    expect(() => service.authorize(p.id, '1234')).toThrow(ApiError);
    service.cancel(p.id);
    expect(() => service.continue(p.id)).toThrow(ApiError);
    expect(() => service.authorize(p.id, '1234')).toThrow(ApiError);
  });

  it('rejects invalid input', async () => {
    const { service } = setup();
    await expect(service.create({ recipient: 'not a handle', amount: 100 })).rejects.toThrow(ApiError);
    await expect(service.create({ recipient: 'rahul.verma@trustpay', amount: 9e9 })).rejects.toThrow(ApiError);
  });
});

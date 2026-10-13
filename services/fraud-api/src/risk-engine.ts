import { deterministicExplanation } from '../../agents/src/index';
import { networkFacts, VELOCITY_MIN_SENDERS, VELOCITY_WINDOW_HOURS } from './graph';
import type {
  Baseline,
  Beneficiary,
  RecommendedAction,
  RiskAssessment,
  RiskLevel,
  RiskSignal,
  ScamCheckAnswers,
} from './models';
import type { Store } from './store';

export interface RiskConfig {
  mediumAt: number;
  highAt: number;
  holdSeconds: number;
  amountRatioCaution: number;
  amountRatioHigh: number;
  newAccountDays: number;
  /** Without network/complaint evidence, score is capped here unless context is strong. */
  unsupportedCap: number;
  strongContextPoints: number;
}

export const DEFAULT_CONFIG: RiskConfig = {
  mediumAt: 30,
  highAt: 60,
  holdSeconds: Number(process.env['HOLD_SECONDS'] ?? 120),
  amountRatioCaution: 3,
  amountRatioHigh: 6,
  newAccountDays: 14,
  unsupportedCap: 59,
  strongContextPoints: 40,
};

const DAY = 24 * 3600_000;
const inr = (n: number) => `₹${n.toLocaleString('en-IN')}`;

export function computeBaseline(store: Store, customerId: string): Baseline {
  const done = store.transactions.filter((t) => t.customerId === customerId && t.status === 'COMPLETED');
  if (done.length === 0) return { avgAmount: 0, maxAmount: 0, txnCount: 0 };
  const total = done.reduce((s, t) => s + t.amount, 0);
  return {
    avgAmount: Math.round(total / done.length),
    maxAmount: Math.max(...done.map((t) => t.amount)),
    txnCount: done.length,
  };
}

export interface AssessInput {
  store: Store;
  customerId: string;
  beneficiary: Beneficiary;
  amount: number;
  answers?: ScamCheckAnswers;
  config?: RiskConfig;
}

/** Pure, deterministic scoring. Each signal is a separate evidence item. */
export function assess(input: AssessInput): RiskAssessment {
  const { store, customerId, beneficiary, amount, answers } = input;
  const cfg = input.config ?? DEFAULT_CONFIG;
  const signals: RiskSignal[] = [];
  const graphIds = new Set<string>([beneficiary.id]);

  // 1. Amount vs the customer's own baseline.
  const base = computeBaseline(store, customerId);
  if (base.avgAmount > 0 && amount > base.maxAmount) {
    const ratio = amount / base.avgAmount;
    if (ratio >= cfg.amountRatioCaution) {
      const strong = ratio >= cfg.amountRatioHigh;
      signals.push({
        id: 'amount.deviation',
        category: 'amount',
        severity: 'caution',
        title: 'Unusual amount',
        evidence: `${inr(amount)} is about ${Math.round(ratio)}× your average payment of ${inr(base.avgAmount)} and above your largest recent payment of ${inr(base.maxAmount)}.`,
        points: strong ? 20 : 15,
        sourceEntityIds: [customerId],
      });
    }
  }

  // 2. Beneficiary familiarity and profile.
  const paidBefore = store.transactions.some(
    (t) => t.customerId === customerId && t.beneficiaryId === beneficiary.id && t.status === 'COMPLETED',
  );
  if (!paidBefore) {
    signals.push({
      id: 'beneficiary.unfamiliar',
      category: 'beneficiary',
      severity: 'info',
      title: 'First payment to this recipient',
      evidence: 'You have not paid this recipient before.',
      points: 5,
      sourceEntityIds: [beneficiary.id],
    });
  }
  const ageDays = beneficiary.firstSeenAt
    ? (store.clock().getTime() - new Date(beneficiary.firstSeenAt).getTime()) / DAY
    : undefined;
  if (ageDays !== undefined && ageDays >= 0 && ageDays < cfg.newAccountDays) {
    signals.push({
      id: 'beneficiary.new_account',
      category: 'beneficiary',
      severity: 'caution',
      title: 'Recently created recipient handle',
      evidence: `This recipient handle was first seen ${Math.max(1, Math.round(ageDays))} day(s) ago.`,
      points: 5,
      sourceEntityIds: [beneficiary.id],
    });
  }
  if (beneficiary.complaintCount > 0) {
    signals.push({
      id: 'beneficiary.complaints',
      category: 'beneficiary',
      severity: 'high',
      title: 'Prior complaints on record',
      evidence: `${beneficiary.complaintCount} synthetic complaint(s) are recorded against this recipient.`,
      points: 25,
      sourceEntityIds: [beneficiary.id],
    });
  }

  // 3. Fraud network graph.
  const facts = networkFacts(store, beneficiary.id);
  if (facts.recentSenderIds.length >= VELOCITY_MIN_SENDERS) {
    facts.recentSenderIds.forEach((id) => graphIds.add(id));
    signals.push({
      id: 'network.velocity',
      category: 'network',
      severity: 'caution',
      title: 'Burst of incoming transfers',
      evidence: `This recipient received transfers from ${facts.recentSenderIds.length} different senders in the last ${VELOCITY_WINDOW_HOURS} hours.`,
      points: 10,
      sourceEntityIds: [beneficiary.id, ...facts.recentSenderIds],
    });
  }
  if (facts.flaggedNeighborIds.length > 0) {
    facts.flaggedNeighborIds.forEach((id) => graphIds.add(id));
    const n = facts.flaggedNeighborIds.length;
    signals.push({
      id: 'network.flagged_links',
      category: 'network',
      severity: 'high',
      title: 'Linked to flagged accounts',
      evidence: `This recipient has direct transfer links to ${n} account${n > 1 ? 's' : ''} flagged in the synthetic fraud network.`,
      points: n >= 2 ? 15 : 10,
      sourceEntityIds: [beneficiary.id, ...facts.flaggedNeighborIds],
    });
  }

  // 4. Scam context from the user's answers (only counted once supplied).
  if (answers) {
    if (answers.sourceOfDetails === 'MESSAGING_APP') {
      signals.push({
        id: 'context.source',
        category: 'context',
        severity: 'high',
        title: 'Details received on a messaging app',
        evidence: 'You said you received these payment details on Telegram/WhatsApp.',
        points: 15,
        sourceEntityIds: [],
      });
    } else if (answers.sourceOfDetails === 'ONLINE_JOB_SITE') {
      signals.push({
        id: 'context.source',
        category: 'context',
        severity: 'caution',
        title: 'Details received from an online job site',
        evidence: 'You said you received these payment details from an online job site.',
        points: 8,
        sourceEntityIds: [],
      });
    }
    if (answers.promisedBenefit === 'YES') {
      signals.push({
        id: 'context.promise',
        category: 'context',
        severity: 'high',
        title: 'Guaranteed returns or payouts promised',
        evidence: 'You said guaranteed returns, task payouts, or a job were promised in exchange for this payment.',
        points: 25,
        sourceEntityIds: [],
      });
    }
  }

  const raw = signals.reduce((s, x) => s + x.points, 0);
  const contextPoints = signals.filter((s) => s.category === 'context').reduce((s, x) => s + x.points, 0);
  const hasEvidence = signals.some(
    (s) => s.category === 'network' || s.id === 'beneficiary.complaints',
  );
  // Newness or an unusual amount alone must never look like fraud.
  const capped = !hasEvidence && contextPoints < cfg.strongContextPoints ? Math.min(raw, cfg.unsupportedCap) : raw;
  const score = Math.max(0, Math.min(100, capped));

  const level: RiskLevel = score >= cfg.highAt ? 'HIGH' : score >= cfg.mediumAt ? 'MEDIUM' : 'LOW';
  const recommendedAction: RecommendedAction =
    level === 'HIGH' ? 'HOLD' : level === 'MEDIUM' ? 'REVIEW' : 'PROCEED';

  const explanation = deterministicExplanation({
    score,
    level,
    action: recommendedAction,
    amount,
    signals,
  }).summary;

  return {
    score,
    level,
    signals,
    recommendedAction,
    beneficiaryId: beneficiary.id,
    graphEntityIds: [...graphIds],
    explanation,
    holdSeconds: recommendedAction === 'HOLD' ? cfg.holdSeconds : 0,
  };
}

import { randomUUID } from 'node:crypto';
import type { AgentProvider, AgentContext } from '../../agents/src/index';
import { assess, DEFAULT_CONFIG, type RiskConfig } from './risk-engine';
import type {
  Beneficiary,
  Payment,
  Question,
  RiskAssessment,
  ScamCheckAnswers,
  TraceEntry,
  Transaction,
} from './models';
import { CUSTOMER_ID, type Store } from './store';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const HANDLE_RE = /^[a-z0-9._-]{2,40}@[a-z]{2,15}$/i;
const ACCOUNT_RE = /^\d{9,18}$/;

const OPTIONS: Record<Question['id'], Question['options']> = {
  sourceOfDetails: [
    { value: 'FRIEND_FAMILY', label: 'A friend or family member' },
    { value: 'MESSAGING_APP', label: 'Telegram or WhatsApp' },
    { value: 'ONLINE_JOB_SITE', label: 'An online job site' },
  ],
  promisedBenefit: [
    { value: 'YES', label: 'Yes' },
    { value: 'NO', label: 'No' },
  ],
};

const SOURCES = new Set(OPTIONS.sourceOfDetails.map((o) => o.value));
const PROMISES = new Set(OPTIONS.promisedBenefit.map((o) => o.value));

export function resolveBeneficiary(store: Store, recipient: string): Beneficiary {
  const q = recipient.trim();
  const known = [...store.beneficiaries.values()].find((b) => b.handle.toLowerCase() === q.toLowerCase());
  if (known) return known;
  if (!HANDLE_RE.test(q) && !ACCOUNT_RE.test(q)) {
    throw new ApiError(400, 'Enter a valid UPI ID (name@bank) or a 9–18 digit account number.');
  }
  const isAccount = ACCOUNT_RE.test(q);
  return {
    id: `ben_custom_${q.toLowerCase().replace(/[^a-z0-9]/g, '_')}`,
    displayName: 'Unverified recipient',
    handle: isAccount ? `Account ${q}` : q,
    maskedAccount: isAccount ? `XXXXXX${q.slice(-4)}` : 'Not available',
    bankLabel: 'Unknown bank',
    complaintCount: 0,
  };
}

export class PaymentService {
  private payments = new Map<string, Payment>();

  constructor(
    private store: Store,
    private agents: AgentProvider,
    private config: RiskConfig = DEFAULT_CONFIG,
  ) {}

  private now(): Date {
    return this.store.clock();
  }

  private log(p: Payment, actor: TraceEntry['actor'], message: string): void {
    p.trace.push({ at: this.now().toISOString(), actor, message });
  }

  list(): Payment[] {
    return [...this.payments.values()].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }

  get(id: string): Payment {
    const p = this.payments.get(id);
    if (!p) throw new ApiError(404, 'Payment not found');
    return p;
  }

  private ctx(a: RiskAssessment, amount: number): AgentContext {
    return {
      score: a.score,
      level: a.level,
      action: a.recommendedAction,
      amount,
      signals: a.signals,
    };
  }

  async create(input: { recipient: string; amount: number; note?: string; scenarioId?: string }): Promise<Payment> {
    const customer = this.store.customers.get(CUSTOMER_ID)!;
    const amount = Number(input.amount);
    if (!Number.isFinite(amount) || amount < 1 || amount > 1_000_000) {
      throw new ApiError(400, 'Enter an amount between ₹1 and ₹10,00,000.');
    }
    if (amount > customer.balance) throw new ApiError(400, 'Amount exceeds available balance.');
    const note = String(input.note ?? '').slice(0, 80);
    const beneficiary = resolveBeneficiary(this.store, String(input.recipient ?? ''));

    const assessment = assess({
      store: this.store,
      customerId: CUSTOMER_ID,
      beneficiary,
      amount,
      config: this.config,
    });

    const payment: Payment = {
      id: `pay_${randomUUID().slice(0, 8)}`,
      customerId: CUSTOMER_ID,
      beneficiary,
      amount,
      note,
      status: assessment.recommendedAction === 'PROCEED' ? 'READY_FOR_AUTH' : 'SCAM_CHECK',
      assessment,
      initialAssessment: assessment,
      questions: [],
      explanation: { headline: '', summary: '', signalIds: [], provider: 'mock' },
      createdAt: this.now().toISOString(),
      trace: [],
      simulated: true,
    };
    this.log(payment, 'payment-orchestrator', `Payment of ₹${amount} to ${beneficiary.handle} created (simulated).`);
    this.log(
      payment,
      'risk-engine',
      `Pre-authorization assessment: score ${assessment.score}, ${assessment.level}, action ${assessment.recommendedAction}. Signals: ${assessment.signals.map((s) => `${s.id}(+${s.points})`).join(', ') || 'none'}.`,
    );

    if (payment.status === 'SCAM_CHECK') {
      const q = await this.agents.selectQuestions(this.ctx(assessment, amount));
      payment.questions = q.value.map((x) => ({ id: x.id, text: x.text, options: OPTIONS[x.id] }));
      this.log(
        payment,
        'scam-check-agent',
        `Selected ${payment.questions.length} scam-check question(s) via ${q.provider}${q.fallbackReason ? ` (fallback: ${q.fallbackReason})` : ''}.`,
      );
      await this.explain(payment);
    } else {
      this.log(payment, 'payment-orchestrator', 'Low risk: no scam check required. Proceeding to PIN step.');
      payment.explanation = {
        headline: 'Nothing unusual found',
        summary: assessment.explanation,
        signalIds: [],
        provider: 'mock',
      };
    }
    this.payments.set(payment.id, payment);
    return payment;
  }

  private async explain(p: Payment): Promise<void> {
    const out = await this.agents.explain(this.ctx(p.assessment, p.amount));
    p.explanation = { ...out.value, provider: out.provider };
    this.log(
      p,
      'explainer-agent',
      `Explanation generated via ${out.provider}${out.fallbackReason ? ` (fallback: ${out.fallbackReason})` : ''}; cites ${out.value.signalIds.join(', ') || 'no signals'}.`,
    );
  }

  async submitAnswers(id: string, raw: Partial<ScamCheckAnswers>): Promise<Payment> {
    const p = this.get(id);
    if (p.status !== 'SCAM_CHECK') throw new ApiError(409, 'Scam check is not pending for this payment.');
    if (!raw.sourceOfDetails || !SOURCES.has(raw.sourceOfDetails) || !raw.promisedBenefit || !PROMISES.has(raw.promisedBenefit)) {
      throw new ApiError(400, 'Both scam-check answers are required.');
    }
    const answers: ScamCheckAnswers = { sourceOfDetails: raw.sourceOfDetails, promisedBenefit: raw.promisedBenefit };
    p.answers = answers;
    p.assessment = assess({
      store: this.store,
      customerId: p.customerId,
      beneficiary: p.beneficiary,
      amount: p.amount,
      answers,
      config: this.config,
    });
    const a = p.assessment;
    this.log(
      p,
      'risk-engine',
      `Re-assessed with answers (${answers.sourceOfDetails}, promised=${answers.promisedBenefit}): score ${a.score}, ${a.level}, action ${a.recommendedAction}.`,
    );
    // The deterministic action alone drives state; agents only supply wording.
    if (a.recommendedAction === 'HOLD') {
      p.status = 'HOLD';
      p.holdUntil = new Date(this.now().getTime() + a.holdSeconds * 1000).toISOString();
      this.log(p, 'payment-orchestrator', `Simulated hold started for ${a.holdSeconds}s. PIN step locked.`);
    } else if (a.recommendedAction === 'REVIEW') {
      p.status = 'REVIEW';
      this.log(p, 'payment-orchestrator', 'Review required: user must acknowledge warning before PIN step.');
    } else {
      p.status = 'READY_FOR_AUTH';
    }
    await this.explain(p);
    return p;
  }

  /** Acknowledge a REVIEW warning, or leave a HOLD once its simulated timer has elapsed. */
  continue(id: string): Payment {
    const p = this.get(id);
    if (p.status === 'REVIEW') {
      p.status = 'READY_FOR_AUTH';
      this.log(p, 'payment-orchestrator', 'User acknowledged the warning. PIN step unlocked.');
    } else if (p.status === 'HOLD') {
      const remaining = new Date(p.holdUntil!).getTime() - this.now().getTime();
      if (remaining > 0) {
        throw new ApiError(409, `Simulated hold still active for ${Math.ceil(remaining / 1000)}s.`);
      }
      p.status = 'READY_FOR_AUTH';
      this.log(p, 'payment-orchestrator', 'Simulated hold elapsed. PIN step unlocked.');
    } else {
      throw new ApiError(409, `Cannot continue from status ${p.status}.`);
    }
    return p;
  }

  authorize(id: string, pin: unknown): Payment {
    const p = this.get(id);
    if (p.status !== 'READY_FOR_AUTH') {
      throw new ApiError(409, 'Authorization is not available for this payment yet.');
    }
    // Dummy PIN only: validated for shape, never stored or logged.
    if (typeof pin !== 'string' || !/^\d{4,6}$/.test(pin)) {
      throw new ApiError(400, 'Enter a 4–6 digit demo PIN.');
    }
    const customer = this.store.customers.get(p.customerId)!;
    if (p.amount > customer.balance) throw new ApiError(400, 'Amount exceeds available balance.');
    customer.balance -= p.amount;
    const txn: Transaction = {
      id: `txn_${p.id}`,
      customerId: p.customerId,
      beneficiaryId: p.beneficiary.id,
      amount: p.amount,
      currency: 'INR',
      note: p.note,
      timestamp: this.now().toISOString(),
      status: 'COMPLETED',
    };
    if (!this.store.beneficiaries.has(p.beneficiary.id)) {
      this.store.beneficiaries.set(p.beneficiary.id, { ...p.beneficiary, firstSeenAt: this.now().toISOString() });
    }
    this.store.addTransaction(txn);
    p.status = 'COMPLETED';
    this.log(p, 'payment-orchestrator', 'Simulated payment completed. No real money moved.');
    return p;
  }

  cancel(id: string): Payment {
    const p = this.get(id);
    if (p.status === 'COMPLETED' || p.status === 'CANCELLED') {
      throw new ApiError(409, `Payment already ${p.status.toLowerCase()}.`);
    }
    p.status = 'CANCELLED';
    delete p.holdUntil;
    this.log(p, 'payment-orchestrator', 'Payment cancelled by user.');
    return p;
  }
}

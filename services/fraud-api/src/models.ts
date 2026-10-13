// Shared contracts. Mirrored in apps/banking-web/src/app/models.ts — keep in sync.

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type RecommendedAction = 'PROCEED' | 'REVIEW' | 'HOLD' | 'CANCEL';
export type Severity = 'info' | 'caution' | 'high';
export type SignalCategory = 'amount' | 'beneficiary' | 'network' | 'context';

export interface CustomerProfile {
  id: string;
  displayName: string;
  upiHandle: string;
  balance: number;
}

export interface Baseline {
  avgAmount: number;
  maxAmount: number;
  txnCount: number;
}

export interface Beneficiary {
  id: string;
  displayName: string;
  handle: string;
  maskedAccount: string;
  bankLabel: string;
  /** Unknown for recipients absent from synthetic records. */
  firstSeenAt?: string;
  /** Synthetic fraud-intel label. Absent for unknown/custom beneficiaries. */
  syntheticRisk?: 'FLAGGED';
  /** Prior complaints in synthetic records. */
  complaintCount: number;
}

export type TransactionStatus = 'COMPLETED' | 'CANCELLED';

export interface Transaction {
  id: string;
  customerId: string;
  beneficiaryId: string;
  amount: number;
  currency: 'INR';
  note: string;
  timestamp: string;
  status: TransactionStatus;
  scenarioId?: string;
}

export interface RiskSignal {
  id: string;
  category: SignalCategory;
  severity: Severity;
  title: string;
  evidence: string;
  points: number;
  sourceEntityIds: string[];
}

export type SourceOfDetails = 'FRIEND_FAMILY' | 'MESSAGING_APP' | 'ONLINE_JOB_SITE';
export type PromisedBenefit = 'YES' | 'NO';

export interface ScamCheckAnswers {
  sourceOfDetails: SourceOfDetails;
  promisedBenefit: PromisedBenefit;
}

export interface RiskAssessment {
  score: number;
  level: RiskLevel;
  signals: RiskSignal[];
  recommendedAction: RecommendedAction;
  beneficiaryId: string;
  graphEntityIds: string[];
  explanation: string;
  holdSeconds: number;
}

export interface GraphNode {
  id: string;
  type: 'customer' | 'beneficiary';
  label: string;
  riskLevel: 'NORMAL' | 'WATCH' | 'FLAGGED';
  metadata: Record<string, string | number>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  amount: number;
  timestamp: string;
  status: TransactionStatus;
}

export interface Question {
  id: 'sourceOfDetails' | 'promisedBenefit';
  text: string;
  options: { value: string; label: string }[];
}

export interface Explanation {
  headline: string;
  summary: string;
  /** Signal ids the text is grounded in. */
  signalIds: string[];
  provider: 'mock' | 'gemini' | 'mock-fallback';
}

export interface TraceEntry {
  at: string;
  actor: 'risk-engine' | 'scam-check-agent' | 'explainer-agent' | 'payment-orchestrator';
  message: string;
}

export type PaymentStatus =
  | 'SCAM_CHECK'
  | 'REVIEW'
  | 'HOLD'
  | 'READY_FOR_AUTH'
  | 'COMPLETED'
  | 'CANCELLED';

export interface Payment {
  id: string;
  customerId: string;
  beneficiary: Beneficiary;
  amount: number;
  note: string;
  status: PaymentStatus;
  assessment: RiskAssessment;
  initialAssessment: RiskAssessment;
  answers?: ScamCheckAnswers;
  questions: Question[];
  explanation: Explanation;
  holdUntil?: string;
  createdAt: string;
  trace: TraceEntry[];
  simulated: true;
}

export interface Scenario {
  id: string;
  title: string;
  description: string;
  handle: string;
  amount: number;
  note: string;
  expectedOutcome: string;
  suggestedAnswers?: ScamCheckAnswers;
}

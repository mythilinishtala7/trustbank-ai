// Mirrors services/fraud-api/src/models.ts — keep in sync.

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type RecommendedAction = 'PROCEED' | 'REVIEW' | 'HOLD' | 'CANCEL';
export type Severity = 'info' | 'caution' | 'high';

export interface Customer {
  id: string;
  displayName: string;
  upiHandle: string;
  balance: number;
}

export interface Beneficiary {
  id: string;
  displayName: string;
  handle: string;
  maskedAccount: string;
  bankLabel: string;
  firstSeenAt?: string;
  complaintCount: number;
}

export interface TransactionView {
  id: string;
  beneficiaryId: string;
  beneficiary?: Beneficiary;
  amount: number;
  note: string;
  timestamp: string;
  status: 'COMPLETED' | 'CANCELLED';
}

export interface MeResponse {
  customer: Customer;
  baseline: { avgAmount: number; maxAmount: number; txnCount: number };
  transactions: TransactionView[];
  agentProvider: 'mock' | 'gemini';
}

export interface RiskSignal {
  id: string;
  category: 'amount' | 'beneficiary' | 'network' | 'context';
  severity: Severity;
  title: string;
  evidence: string;
  points: number;
  sourceEntityIds: string[];
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

export type SourceOfDetails = 'FRIEND_FAMILY' | 'MESSAGING_APP' | 'ONLINE_JOB_SITE';
export type PromisedBenefit = 'YES' | 'NO';

export interface ScamCheckAnswers {
  sourceOfDetails: SourceOfDetails;
  promisedBenefit: PromisedBenefit;
}

export interface Question {
  id: 'sourceOfDetails' | 'promisedBenefit';
  text: string;
  options: { value: string; label: string }[];
}

export interface Explanation {
  headline: string;
  summary: string;
  signalIds: string[];
  provider: 'mock' | 'gemini' | 'mock-fallback';
}

export interface TraceEntry {
  at: string;
  actor: 'risk-engine' | 'scam-check-agent' | 'explainer-agent' | 'payment-orchestrator';
  message: string;
}

export type PaymentStatus = 'SCAM_CHECK' | 'REVIEW' | 'HOLD' | 'READY_FOR_AUTH' | 'COMPLETED' | 'CANCELLED';

export interface Payment {
  id: string;
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
  status: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  simulated: true;
}

export interface NodeDetail {
  node: GraphNode;
  observations: string[];
  connections: { nodeId: string; label: string; direction: 'in' | 'out'; amount: number; timestamp: string }[];
  disclaimer: string;
}

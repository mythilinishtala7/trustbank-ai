export type Provenance = 'VERIFIED_SYNTHETIC' | 'INFERRED' | 'USER_PROVIDED';
export type FindingStatus = 'OK' | 'FAILED' | 'TIMEOUT' | 'DEGRADED';
export type AgentId = 'anomaly' | 'fraud_network' | 'questionnaire';
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type PolicyAction = 'PROCEED' | 'REVIEW' | 'HOLD';
export type GraphLabel = 'Customer' | 'Account' | 'Transaction' | 'Beneficiary' | 'RiskSignal';
export type GraphEdgeType = 'OWNS' | 'SENT' | 'PAID' | 'CONNECTED_TO' | 'FLAGGED_FOR';

export interface InvestigatorToken {
  token: string;
  role: 'investigator';
  expiresAt: string;
}

export interface TransactionListItem {
  transactionId: string;
  customerName: string;
  recipientName: string;
  amount: number;
  status: string;
  createdAt: string;
}

export interface TransactionSummary {
  customerId: string;
  customerName: string;
  recipientId: string;
  recipientName: string;
  amount: number;
  note: string;
  timestamp: string;
  status: string;
}

export interface Evidence {
  id: string;
  summary: string;
  provenance: Provenance;
  sourceEntityIds: string[];
  points: number;
}

export interface Finding {
  agentId: AgentId;
  status: FindingStatus;
  score: number;
  confidence: number;
  error: string | null;
  evidence: Evidence[];
}

export interface Aggregate {
  anomalyScore: number;
  networkScore: number;
  preScore: number;
  contextPoints: number;
  finalScore: number;
  level: RiskLevel;
  action: PolicyAction;
  elevated: boolean;
  incomplete: boolean;
  evidenceCapApplied: boolean;
}

export interface PolicyConfig {
  anomalyWeight: number;
  networkWeight: number;
  elevatedThreshold: number;
  highThreshold: number;
  holdSeconds: number;
  contextCap: number;
  evidenceCapScore: number;
  evidenceCapContext: number;
}

export interface QuestionOption {
  value: string;
  label: string;
}

export interface Question {
  id: string;
  text: string;
  options: QuestionOption[];
  allowFreeText?: boolean;
}

export interface Answer {
  questionId: string;
  option: string;
  freeText: string | null;
}

export interface AssessmentExplanation {
  text: string;
  reasons: string[];
  evidenceIds: string[];
  status: 'OK' | 'DEGRADED';
}

export interface ToolCall {
  agentId: string;
  tool: string;
  parameters: Record<string, unknown>;
  resultSummary: string;
  startedAt: string;
  durationMs: number;
}

export interface Assessment {
  id: string;
  stage: 'INITIAL' | 'FINAL';
  createdAt: string;
  complete: boolean;
  findings: Finding[];
  aggregate: Aggregate;
  config: PolicyConfig;
  questions: Question[];
  answers: Answer[];
  explanation: AssessmentExplanation | null;
  model: string | null;
  toolCalls: ToolCall[];
  startedAt: string;
  endedAt: string;
  durationMs: number;
}

export interface GraphNode {
  id: string;
  label: GraphLabel;
  name: string;
  highlighted: boolean;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: GraphEdgeType;
  provenance: Provenance | null;
  kind: string | null;
  highlighted: boolean;
}

export interface InvestigationGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
}

export interface TransactionDetail {
  transactionId: string;
  kind: 'PAYMENT' | 'HISTORICAL';
  simulated: boolean;
  summary: TransactionSummary;
  assessments: Assessment[];
  graph: InvestigationGraph;
}

export interface TraceEvent {
  seq: number;
  at: string;
  agentId: string;
  type: 'STARTED' | 'TOOL_CALL' | 'FINDING' | 'FALLBACK' | 'COMPLETED' | 'FAILED' | 'STATE_CHANGE';
  status: string | null;
  durationMs: number | null;
  tool: string | null;
  parameters: Record<string, unknown> | null;
  resultSummary: string | null;
  message: string;
}

export interface TimelineResponse {
  transactionId: string;
  paymentStatus: string | null;
  done: boolean;
  events: TraceEvent[];
}

export interface EvidenceRef {
  stage: 'INITIAL' | 'FINAL';
  agentId: AgentId;
  evidence: Evidence;
}

export const IN_FLIGHT_STATUSES: readonly string[] = ['INITIATED', 'ASSESSING', 'QUESTIONNAIRE'];

export function isInFlight(status: string | null | undefined): boolean {
  return !!status && IN_FLIGHT_STATUSES.includes(status);
}

export const PROVENANCE_LABELS: Record<Provenance, { label: string; hint: string; glyph: string }> = {
  VERIFIED_SYNTHETIC: { label: 'Verified synthetic', hint: 'Declared in the synthetic fixtures as a fact about a relationship', glyph: '◆' },
  INFERRED: { label: 'Inferred', hint: 'Computed from transaction behaviour at assessment time', glyph: '◌' },
  USER_PROVIDED: { label: 'User provided', hint: "From the customer's questionnaire answers", glyph: '✎' },
};

export function buildEvidenceIndex(assessments: Assessment[]): Map<string, EvidenceRef[]> {
  const index = new Map<string, EvidenceRef[]>();
  for (const a of assessments) {
    for (const f of a.findings) {
      for (const evidence of f.evidence) {
        for (const id of evidence.sourceEntityIds) {
          const list = index.get(id) ?? [];
          list.push({ stage: a.stage, agentId: f.agentId, evidence });
          index.set(id, list);
        }
      }
    }
  }
  return index;
}

export type Severity = 'info' | 'caution' | 'high';

/** Only verified, deterministic evidence is passed to agents. No free-text user input. */
export interface EvidenceSignal {
  id: string;
  category: 'amount' | 'beneficiary' | 'network' | 'context';
  severity: Severity;
  title: string;
  evidence: string;
}

export interface AgentContext {
  score: number;
  level: 'LOW' | 'MEDIUM' | 'HIGH';
  /** Deterministic action. Agents may phrase it, never change it. */
  action: 'PROCEED' | 'REVIEW' | 'HOLD' | 'CANCEL';
  amount: number;
  signals: EvidenceSignal[];
}

export type QuestionId = 'sourceOfDetails' | 'promisedBenefit';

export interface QuestionPrompt {
  id: QuestionId;
  text: string;
}

export interface ExplanationResult {
  headline: string;
  summary: string;
  signalIds: string[];
}

export interface AgentOutcome<T> {
  value: T;
  provider: 'mock' | 'gemini' | 'mock-fallback';
  /** Present when an external agent failed validation or errored. */
  fallbackReason?: string;
}

export interface AgentProvider {
  readonly name: 'mock' | 'gemini';
  selectQuestions(ctx: AgentContext): Promise<AgentOutcome<QuestionPrompt[]>>;
  explain(ctx: AgentContext): Promise<AgentOutcome<ExplanationResult>>;
}

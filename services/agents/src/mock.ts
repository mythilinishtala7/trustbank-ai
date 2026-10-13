import type {
  AgentContext,
  AgentOutcome,
  AgentProvider,
  ExplanationResult,
  QuestionPrompt,
} from './types';

export const DEFAULT_QUESTIONS: QuestionPrompt[] = [
  { id: 'sourceOfDetails', text: 'How did you get this recipient’s payment details?' },
  {
    id: 'promisedBenefit',
    text: 'Were you promised guaranteed returns, task payouts, or a job in exchange for this payment?',
  },
];

const SEVERITY_RANK = { high: 2, caution: 1, info: 0 } as const;

export function deterministicExplanation(ctx: AgentContext): ExplanationResult {
  const top = [...ctx.signals]
    .filter((s) => s.severity !== 'info')
    .sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity])
    .slice(0, 3);

  if (top.length === 0) {
    return {
      headline: 'Nothing unusual found',
      summary: 'This payment matches your usual activity and no risk indicators were found.',
      signalIds: [],
    };
  }

  const headline =
    ctx.level === 'HIGH'
      ? 'We paused this payment to protect you'
      : 'Please double-check this payment';
  const summary =
    `Based on the signals we verified: ` +
    top.map((s) => s.evidence).join(' ') +
    ' These are warning signs, not proof of fraud.';
  return { headline, summary, signalIds: top.map((s) => s.id) };
}

export class MockAgentProvider implements AgentProvider {
  readonly name = 'mock' as const;

  async selectQuestions(): Promise<AgentOutcome<QuestionPrompt[]>> {
    return { value: DEFAULT_QUESTIONS, provider: 'mock' };
  }

  async explain(ctx: AgentContext): Promise<AgentOutcome<ExplanationResult>> {
    return { value: deterministicExplanation(ctx), provider: 'mock' };
  }
}

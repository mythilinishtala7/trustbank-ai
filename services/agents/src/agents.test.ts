import { describe, expect, it } from 'vitest';
import { AdkAgentProvider } from './adk';
import { MockAgentProvider } from './mock';
import type { AgentContext } from './types';

const ctx: AgentContext = {
  score: 95,
  level: 'HIGH',
  action: 'HOLD',
  amount: 25000,
  signals: [
    {
      id: 'network.links',
      category: 'network',
      severity: 'high',
      title: 'Linked to flagged accounts',
      evidence: 'Recipient is connected to 2 accounts flagged in the synthetic network.',
    },
    {
      id: 'context.promise',
      category: 'context',
      severity: 'high',
      title: 'Promised returns',
      evidence: 'You said guaranteed returns or payouts were promised.',
    },
  ],
};

describe('agents', () => {
  it('mock provider explains only supplied signals', async () => {
    const out = await new MockAgentProvider().explain(ctx);
    expect(out.provider).toBe('mock');
    expect(out.value.signalIds).toEqual(['network.links', 'context.promise']);
  });

  it('uses valid Gemini output', async () => {
    const provider = new AdkAgentProvider({
      runJson: async () => ({
        headline: 'Pause and verify',
        summary: 'The recipient is linked to flagged accounts and returns were promised.',
        signalIds: ['network.links'],
      }),
    });
    const out = await provider.explain(ctx);
    expect(out.provider).toBe('gemini');
  });

  it('falls back when output cites an invented signal', async () => {
    const provider = new AdkAgentProvider({
      runJson: async () => ({
        headline: 'Pause and verify',
        summary: 'The recipient has 14 prior complaints from other customers.',
        signalIds: ['invented.complaints'],
      }),
    });
    const out = await provider.explain(ctx);
    expect(out.provider).toBe('mock-fallback');
    expect(out.value.signalIds).not.toContain('invented.complaints');
  });

  it('falls back when the model call throws', async () => {
    const provider = new AdkAgentProvider({
      runJson: async () => {
        throw new Error('503 unavailable');
      },
    });
    const q = await provider.selectQuestions(ctx);
    expect(q.provider).toBe('mock-fallback');
    expect(q.value).toHaveLength(2);
  });
});

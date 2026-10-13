import cors from 'cors';
import express, { type NextFunction, type Request, type Response } from 'express';
import { createAgentProvider, type AgentProvider } from '../../agents/src/index';
import { buildGraph, nodeDetail } from './graph';
import { ApiError, PaymentService, resolveBeneficiary } from './payments';
import { computeBaseline } from './risk-engine';
import { CUSTOMER_ID, createSeededStore, SCENARIOS, type Store } from './store';

export function createApp(opts: { store?: Store; agents?: AgentProvider } = {}) {
  const store = opts.store ?? createSeededStore(() => new Date());
  const agents = opts.agents ?? createAgentProvider();
  const payments = new PaymentService(store, agents);

  const app = express();
  app.use(cors());
  app.use(express.json({ limit: '10kb' }));

  const wrap =
    (fn: (req: Request, res: Response) => unknown | Promise<unknown>) =>
    (req: Request, res: Response, next: NextFunction) =>
      Promise.resolve(fn(req, res)).catch(next);
  const param = (req: Request, key: string) => String(req.params[key]);

  app.get('/api/health', (_req, res) => {
    res.json({ ok: true, agentProvider: agents.name, simulated: true });
  });

  app.get('/api/me', (_req, res) => {
    res.json({
      customer: store.customers.get(CUSTOMER_ID),
      baseline: computeBaseline(store, CUSTOMER_ID),
      transactions: store.transactions
        .filter((t) => t.customerId === CUSTOMER_ID)
        .map((t) => ({ ...t, beneficiary: store.beneficiaries.get(t.beneficiaryId) })),
      agentProvider: agents.name,
    });
  });

  app.get('/api/scenarios', (_req, res) => {
    res.json(SCENARIOS);
  });

  app.get('/api/recipients/lookup', (req, res) => {
    const b = resolveBeneficiary(store, String(req.query['q'] ?? ''));
    res.json({ displayName: b.displayName, handle: b.handle, maskedAccount: b.maskedAccount, bankLabel: b.bankLabel });
  });

  app.get('/api/payments', (_req, res) => {
    res.json(payments.list());
  });
  app.post(
    '/api/payments',
    wrap(async (req, res) => {
      res.status(201).json(await payments.create(req.body ?? {}));
    }),
  );
  app.get('/api/payments/:id', (req, res) => {
    res.json(payments.get(param(req, 'id')));
  });
  app.post(
    '/api/payments/:id/answers',
    wrap(async (req, res) => {
      res.json(await payments.submitAnswers(param(req, 'id'), req.body ?? {}));
    }),
  );
  app.post('/api/payments/:id/continue', (req, res) => {
    res.json(payments.continue(param(req, 'id')));
  });
  app.post('/api/payments/:id/authorize', (req, res) => {
    res.json(payments.authorize(param(req, 'id'), req.body?.pin));
  });
  app.post('/api/payments/:id/cancel', (req, res) => {
    res.json(payments.cancel(param(req, 'id')));
  });

  app.get('/api/graph', (_req, res) => {
    res.json({ ...buildGraph(store), simulated: true });
  });
  app.get('/api/graph/nodes/:id', (req, res) => {
    const d = nodeDetail(store, param(req, 'id'));
    if (!d) throw new ApiError(404, 'Node not found');
    res.json(d);
  });

  app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof ApiError) {
      res.status(err.status).json({ error: err.message });
      return;
    }
    console.error('Unhandled error:', err instanceof Error ? err.message : err);
    res.status(500).json({ error: 'Something went wrong.' });
  });

  return app;
}

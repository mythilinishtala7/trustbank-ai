import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type {
  GraphResponse,
  MeResponse,
  NodeDetail,
  Payment,
  ScamCheckAnswers,
  Scenario,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  me() {
    return this.http.get<MeResponse>('/api/me');
  }
  scenarios() {
    return this.http.get<Scenario[]>('/api/scenarios');
  }
  lookup(q: string) {
    return this.http.get<{ displayName: string; handle: string; maskedAccount: string; bankLabel: string }>(
      '/api/recipients/lookup',
      { params: { q } },
    );
  }
  createPayment(body: { recipient: string; amount: number; note: string }) {
    return this.http.post<Payment>('/api/payments', body);
  }
  submitAnswers(id: string, answers: ScamCheckAnswers) {
    return this.http.post<Payment>(`/api/payments/${id}/answers`, answers);
  }
  continuePayment(id: string) {
    return this.http.post<Payment>(`/api/payments/${id}/continue`, {});
  }
  authorize(id: string, pin: string) {
    return this.http.post<Payment>(`/api/payments/${id}/authorize`, { pin });
  }
  cancel(id: string) {
    return this.http.post<Payment>(`/api/payments/${id}/cancel`, {});
  }
  payments() {
    return this.http.get<Payment[]>('/api/payments');
  }
  graph() {
    return this.http.get<GraphResponse>('/api/graph');
  }
  nodeDetail(id: string) {
    return this.http.get<NodeDetail>(`/api/graph/nodes/${id}`);
  }
}

export function errorMessage(err: unknown): string {
  const e = err as { error?: { error?: string }; status?: number };
  if (e?.error?.error) return e.error.error;
  if (e?.status === 0) return 'Cannot reach the TrustBank demo API. Is it running on port 3100?';
  return 'Something went wrong. Please try again.';
}

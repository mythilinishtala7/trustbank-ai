import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';
import type {
  Answer,
  ApiError,
  AuthResponse,
  CreatePaymentRequest,
  CustomerPayment,
  Me,
  Persona,
  RecipientLookup,
} from './models';

export const API_BASE = '/api/v1';

export const UNAVAILABLE_MESSAGE = 'TrustBank is temporarily unavailable. Please try again in a moment.';
export const NETWORK_MESSAGE = "We can't reach the server. Check your connection and try again.";

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export function normalizeError(err: unknown): ApiError {
  if (!(err instanceof HttpErrorResponse)) {
    return { kind: 'other', status: -1, code: 'UNKNOWN', message: 'Something went wrong. Please try again.' };
  }
  const body = err.error as { error?: { code?: string; message?: string; requestId?: string } } | null;
  const parsed = body && typeof body === 'object' ? body.error : undefined;
  const code = parsed?.code ?? 'UNKNOWN';
  const requestId = parsed?.requestId ?? err.headers?.get('X-Request-Id') ?? undefined;

  if (err.status === 0) {
    return { kind: 'network', status: 0, code: 'NETWORK', message: NETWORK_MESSAGE };
  }
  if (err.status === 503 || code === 'UNAVAILABLE') {
    return { kind: 'unavailable', status: err.status, code: 'UNAVAILABLE', message: UNAVAILABLE_MESSAGE, requestId };
  }
  const message = parsed?.message || 'Something went wrong. Please try again.';
  const kind =
    err.status === 401
      ? 'unauthenticated'
      : err.status === 404
        ? 'notFound'
        : err.status === 409
          ? 'conflict'
          : err.status === 400 || err.status === 422
            ? 'validation'
            : 'other';
  return { kind, status: err.status, code, message, requestId };
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  personas(): Observable<Persona[]> {
    return this.call(this.http.get<Persona[]>(`${API_BASE}/personas`));
  }

  signIn(personaId: string): Observable<AuthResponse> {
    return this.call(this.http.post<AuthResponse>(`${API_BASE}/auth/customer`, { personaId }));
  }

  me(): Observable<Me> {
    return this.call(this.http.get<Me>(`${API_BASE}/me`));
  }

  lookupRecipient(q: string): Observable<RecipientLookup> {
    return this.call(this.http.get<RecipientLookup>(`${API_BASE}/recipients/lookup`, { params: { q } }));
  }

  /** The same key must be reused when retrying the same attempt so the server can de-duplicate. */
  createPayment(body: CreatePaymentRequest, idempotencyKey: string): Observable<CustomerPayment> {
    const headers = new HttpHeaders({ 'Idempotency-Key': idempotencyKey });
    return this.call(this.http.post<CustomerPayment>(`${API_BASE}/payments`, body, { headers }));
  }

  payment(id: string): Observable<CustomerPayment> {
    return this.call(this.http.get<CustomerPayment>(`${API_BASE}/payments/${encodeURIComponent(id)}`));
  }

  answer(id: string, answers: Answer[]): Observable<CustomerPayment> {
    return this.post(id, 'answers', { answers });
  }

  acknowledge(id: string): Observable<CustomerPayment> {
    return this.post(id, 'acknowledge', {});
  }

  verify(id: string): Observable<CustomerPayment> {
    return this.post(id, 'verify', {});
  }

  continue(id: string): Observable<CustomerPayment> {
    return this.post(id, 'continue', {});
  }

  cancel(id: string): Observable<CustomerPayment> {
    return this.post(id, 'cancel', {});
  }

  authorize(id: string, pin: string): Observable<CustomerPayment> {
    return this.post(id, 'authorize', { pin });
  }

  private post(id: string, action: string, body: unknown): Observable<CustomerPayment> {
    return this.call(this.http.post<CustomerPayment>(`${API_BASE}/payments/${encodeURIComponent(id)}/${action}`, body));
  }

  private call<T>(source: Observable<T>): Observable<T> {
    return source.pipe(catchError((e) => throwError(() => normalizeError(e))));
  }
}

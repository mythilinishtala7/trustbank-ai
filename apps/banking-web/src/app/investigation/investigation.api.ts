import { HttpBackend, HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, tap, throwError } from 'rxjs';
import type { InvestigatorToken, TimelineResponse, TransactionDetail, TransactionListItem } from './investigation.models';
import { InvestigatorSession } from './investigator-session';

export const API_BASE = '/api/v1';

export class InvestigationApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

function toApiError(err: unknown): InvestigationApiError {
  if (err instanceof InvestigationApiError) return err;
  if (err instanceof HttpErrorResponse) {
    const body = err.error as { error?: { code?: string; message?: string } } | null;
    const code = body?.error?.code ?? (err.status === 0 ? 'NETWORK' : 'ERROR');
    const message = body?.error?.message ?? (err.status === 0 ? 'Cannot reach the service.' : 'Request failed.');
    return new InvestigationApiError(err.status, code, message);
  }
  return new InvestigationApiError(0, 'ERROR', 'Request failed.');
}

/** Investigation API client. Uses its own HttpClient (no global interceptors) and attaches the investigator token explicitly. */
@Injectable({ providedIn: 'root' })
export class InvestigationApi {
  private readonly http = new HttpClient(inject(HttpBackend));
  private readonly session = inject(InvestigatorSession);
  private readonly router = inject(Router);

  authenticate(code: string): Observable<InvestigatorToken> {
    return this.http.post<InvestigatorToken>(`${API_BASE}/auth/investigator`, { code }).pipe(
      tap((res) => this.session.signIn(res.token, res.expiresAt)),
      catchError((err) => throwError(() => toApiError(err))),
    );
  }

  recent(limit = 20): Observable<TransactionListItem[]> {
    return this.get<TransactionListItem[]>(`${API_BASE}/investigation/transactions?limit=${limit}`);
  }

  transaction(id: string): Observable<TransactionDetail> {
    return this.get<TransactionDetail>(`${API_BASE}/investigation/transactions/${encodeURIComponent(id)}`);
  }

  timeline(id: string, after = 0): Observable<TimelineResponse> {
    return this.get<TimelineResponse>(`${API_BASE}/investigation/transactions/${encodeURIComponent(id)}/timeline?after=${after}`);
  }

  eventsUrl(id: string, after: number): string {
    return `${API_BASE}/investigation/transactions/${encodeURIComponent(id)}/events?after=${after}`;
  }

  /** Authorization header for fetch-based streaming; null (after redirecting to the gate) when there is no valid token. */
  streamHeaders(): Record<string, string> | null {
    const token = this.session.token();
    if (!token) {
      this.unauthorized();
      return null;
    }
    return { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' };
  }

  unauthorized(): void {
    this.session.clear('Your investigator session ended. Enter the access code again.');
    const returnUrl = this.router.url.startsWith('/investigation/') ? this.router.url : undefined;
    void this.router.navigate(['/investigation'], { queryParams: returnUrl ? { returnUrl } : {} });
  }

  private get<T>(url: string): Observable<T> {
    const token = this.session.token();
    if (!token) {
      this.unauthorized();
      return throwError(() => new InvestigationApiError(401, 'UNAUTHENTICATED', 'Not signed in.'));
    }
    return this.http.get<T>(url, { headers: new HttpHeaders({ Authorization: `Bearer ${token}` }) }).pipe(
      catchError((err) => {
        const e = toApiError(err);
        if (e.status === 401) this.unauthorized();
        return throwError(() => e);
      }),
    );
  }
}

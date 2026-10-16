import { Injectable, InjectionToken, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { InvestigationApi, InvestigationApiError } from './investigation.api';
import { TraceEvent, isInFlight } from './investigation.models';
import { SseParser } from './sse-parser';

export const STREAM_FETCH = new InjectionToken<typeof fetch>('STREAM_FETCH', {
  providedIn: 'root',
  factory: () => (input, init) => fetch(input, init),
});

export interface FeedTiming {
  pollMs: number;
  idleMs: number;
}

export const FEED_TIMING = new InjectionToken<FeedTiming>('FEED_TIMING', {
  providedIn: 'root',
  factory: () => ({ pollMs: 2000, idleMs: 5000 }),
});

export type FeedMode = 'idle' | 'streaming' | 'polling' | 'done';

class Stopped extends Error {}

/**
 * Live trace events for one transaction. Streams over fetch (SSE with an Authorization header) and falls back to
 * polling GET /timeline. Provided per page so it is torn down with the component.
 */
@Injectable()
export class TimelineFeed {
  private readonly api = inject(InvestigationApi);
  private readonly fetchFn = inject(STREAM_FETCH);
  private readonly timing = inject(FEED_TIMING);

  readonly events = signal<TraceEvent[]>([]);
  readonly mode = signal<FeedMode>('idle');
  readonly paymentStatus = signal<string | null>(null);
  readonly error = signal('');
  /** Increments when the server reports a state change, so the page can refresh stored assessments. */
  readonly stateRevision = signal(0);

  private id = '';
  private run = 0;
  private lastSeq = 0;
  private live = false;
  private abort?: AbortController;
  private timer?: ReturnType<typeof setTimeout>;
  private wake?: (value?: unknown) => void;

  start(id: string, initialStatus: string | null): void {
    this.stop();
    this.id = id;
    this.lastSeq = 0;
    this.live = false;
    this.events.set([]);
    this.error.set('');
    this.paymentStatus.set(initialStatus);
    this.mode.set('idle');
    void this.loop(this.run);
  }

  stop(): void {
    this.run++;
    this.abort?.abort();
    this.abort = undefined;
    clearTimeout(this.timer);
    this.wake?.();
    this.wake = undefined;
  }

  private async loop(run: number): Promise<void> {
    let streaming = true;
    try {
      while (run === this.run) {
        const snap = await this.snapshot(run);
        if (!isInFlight(this.paymentStatus())) {
          this.mode.set('done');
          return;
        }
        this.live = true;
        if (streaming) {
          try {
            this.mode.set('streaming');
            await this.stream(run);
            this.mode.set('idle');
            await this.sleep(run, this.timing.idleMs);
            continue;
          } catch (e) {
            if (e instanceof Stopped || run !== this.run) return;
            streaming = false;
          }
        }
        this.mode.set('polling');
        await this.sleep(run, snap.done ? this.timing.idleMs : this.timing.pollMs);
      }
    } catch (e) {
      if (e instanceof Stopped || run !== this.run) return;
      this.mode.set('idle');
      this.error.set(e instanceof InvestigationApiError && e.status !== 401 ? e.message : 'Timeline unavailable.');
    }
  }

  private async snapshot(run: number) {
    const res = await firstValueFrom(this.api.timeline(this.id, this.lastSeq));
    if (run !== this.run) throw new Stopped();
    const previous = this.paymentStatus();
    if (res.paymentStatus) this.paymentStatus.set(res.paymentStatus);
    this.merge(res.events);
    if (this.live && res.paymentStatus && previous && res.paymentStatus !== previous) this.bump();
    return res;
  }

  private async stream(run: number): Promise<void> {
    const headers = this.api.streamHeaders();
    if (!headers) throw new Stopped();
    const ctrl = new AbortController();
    this.abort = ctrl;
    const res = await this.fetchFn(this.api.eventsUrl(this.id, this.lastSeq), { headers, signal: ctrl.signal });
    if (res.status === 401) {
      this.api.unauthorized();
      throw new Stopped();
    }
    const type = res.headers.get('content-type');
    if (!res.ok || !res.body || typeof res.body.getReader !== 'function' || (type && !type.includes('text/event-stream'))) {
      throw new Error('Streaming unavailable');
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    const parser = new SseParser();
    for (;;) {
      const { done, value } = await reader.read();
      if (run !== this.run) {
        void reader.cancel();
        throw new Stopped();
      }
      if (done) return;
      for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
        if (frame.event === 'timeline') {
          try {
            this.merge([JSON.parse(frame.data) as TraceEvent]);
          } catch {
            // malformed frame: skip it, the next snapshot will recover any gap
          }
        } else if (frame.event === 'done') {
          void reader.cancel();
          return;
        }
      }
    }
  }

  private merge(incoming: TraceEvent[]): void {
    if (!incoming.length) return;
    const bySeq = new Map(this.events().map((e) => [e.seq, e]));
    let added = false;
    let stateChange = false;
    for (const e of incoming) {
      if (bySeq.has(e.seq)) continue;
      bySeq.set(e.seq, e);
      added = true;
      stateChange ||= e.type === 'STATE_CHANGE';
      this.lastSeq = Math.max(this.lastSeq, e.seq);
    }
    if (!added) return;
    this.events.set([...bySeq.values()].sort((a, b) => a.seq - b.seq));
    if (this.live && stateChange) this.bump();
  }

  private bump(): void {
    this.stateRevision.update((n) => n + 1);
  }

  private sleep(run: number, ms: number): Promise<void> {
    return new Promise((resolve) => {
      this.wake = resolve;
      this.timer = setTimeout(resolve, ms);
    }).then(() => {
      if (run !== this.run) throw new Stopped();
    });
  }
}

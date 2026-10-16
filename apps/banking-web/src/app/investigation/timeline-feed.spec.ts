import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { InvestigationApi } from './investigation.api';
import type { TimelineResponse } from './investigation.models';
import { traceEvent as testTraceEvent } from './testing/fixtures';
import type { TraceEvent } from './investigation.models';
import { FEED_TIMING, STREAM_FETCH, TimelineFeed } from './timeline-feed';

function sseResponse(chunks: string[], init: ResponseInit = { status: 200, headers: { 'content-type': 'text/event-stream' } }): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((ch) => c.enqueue(enc.encode(ch)));
      c.close();
    },
  });
  return new Response(body, init);
}

const frame = (seq: number, extra: Partial<TraceEvent> = {}) =>
  `event: timeline\nid: ${seq}\ndata: ${JSON.stringify(testTraceEvent(seq, extra))}\n\n`;

const snap = (status: string | null, done: boolean, events = [] as ReturnType<typeof testTraceEvent>[]): TimelineResponse => ({ transactionId: 'txn_1', paymentStatus: status, done, events });

function setup(snapshots: TimelineResponse[], fetchImpl: (url: string, init?: RequestInit) => Promise<Response>) {
  const queue = [...snapshots];
  const api = {
    timeline: vi.fn((_id: string, _after: number) => of(queue.length > 1 ? queue.shift()! : queue[0])),
    streamHeaders: vi.fn(() => ({ Authorization: 'Bearer inv', Accept: 'text/event-stream' }) as Record<string, string> | null),
    eventsUrl: vi.fn((id: string, after: number) => `/api/v1/investigation/transactions/${id}/events?after=${after}`),
    unauthorized: vi.fn(),
  };
  const fetchMock = vi.fn(fetchImpl);
  TestBed.configureTestingModule({
    providers: [
      TimelineFeed,
      { provide: InvestigationApi, useValue: api },
      { provide: STREAM_FETCH, useValue: fetchMock },
      { provide: FEED_TIMING, useValue: { pollMs: 5, idleMs: 5 } },
    ],
  });
  return { api, fetchMock, feed: TestBed.inject(TimelineFeed) };
}

const seqs = (feed: TimelineFeed) => feed.events().map((e) => e.seq);

describe('TimelineFeed streaming', () => {
  it('streams over fetch with the Authorization header, orders and de-dupes by seq, ignores pings', async () => {
    const stream = [': ping\n\n', frame(2), frame(1).slice(0, 30), frame(1).slice(30), frame(2), frame(3), 'event: done\ndata: {}\n\n'];
    const { feed, fetchMock } = setup([snap('ASSESSING', false), snap('READY_FOR_AUTH', true)], async () => sseResponse(stream));
    feed.start('txn_1', 'ASSESSING');
    await vi.waitFor(() => expect(feed.mode()).toBe('done'));
    expect(seqs(feed)).toEqual([1, 2, 3]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/events?after=0');
    expect((init!.headers as Record<string, string>)['Authorization']).toBe('Bearer inv');
  });

  it('after done, reconnects from the last seq only if the payment is still in flight', async () => {
    let n = 0;
    const { feed, fetchMock } = setup([snap('QUESTIONNAIRE', false), snap('QUESTIONNAIRE', false), snap('HOLD_ACTIVE', true)], async () =>
      sseResponse(n++ === 0 ? [frame(1), frame(2), 'event: done\ndata: {}\n\n'] : [frame(3), 'event: done\ndata: {}\n\n']),
    );
    feed.start('txn_1', 'QUESTIONNAIRE');
    await vi.waitFor(() => expect(feed.mode()).toBe('done'));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toContain('after=2');
    expect(seqs(feed)).toEqual([1, 2, 3]);
    expect(feed.paymentStatus()).toBe('HOLD_ACTIVE');
  });

  it('does not stream a payment that is not in flight', async () => {
    const { feed, fetchMock } = setup([snap('HOLD_ACTIVE', true, [testTraceEvent(2), testTraceEvent(1)])], async () => sseResponse([]));
    feed.start('txn_1', 'HOLD_ACTIVE');
    await vi.waitFor(() => expect(feed.mode()).toBe('done'));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(seqs(feed)).toEqual([1, 2]);
  });

  it('bumps stateRevision on a live STATE_CHANGE event', async () => {
    const { feed } = setup([snap('ASSESSING', false), snap('READY_FOR_AUTH', true)], async () =>
      sseResponse([frame(1, { type: 'STATE_CHANGE', agentId: 'policy' }), 'event: done\ndata: {}\n\n']),
    );
    feed.start('txn_1', 'ASSESSING');
    await vi.waitFor(() => expect(feed.mode()).toBe('done'));
    expect(feed.stateRevision()).toBeGreaterThan(0);
  });

  it('stop() ends all activity', async () => {
    const { feed, api } = setup([snap('ASSESSING', false)], async () => sseResponse([frame(1), 'event: done\ndata: {}\n\n']));
    feed.start('txn_1', 'ASSESSING');
    await vi.waitFor(() => expect(seqs(feed)).toEqual([1]));
    feed.stop();
    const calls = api.timeline.mock.calls.length;
    await new Promise((r) => setTimeout(r, 40));
    expect(api.timeline.mock.calls.length).toBe(calls);
  });

  it('on 401 returns to the gate and does not fall back to polling', async () => {
    const { feed, api } = setup([snap('ASSESSING', false)], async () => new Response('', { status: 401 }));
    feed.start('txn_1', 'ASSESSING');
    await vi.waitFor(() => expect(api.unauthorized).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(api.timeline).toHaveBeenCalledTimes(1);
  });
});

describe('TimelineFeed polling fallback', () => {
  it('polls GET /timeline?after=<lastSeq> when fetch fails, and stops when the payment settles', async () => {
    const { feed, api } = setup([snap('ASSESSING', false, [testTraceEvent(1)]), snap('ASSESSING', false, [testTraceEvent(2), testTraceEvent(1)]), snap('READY_FOR_AUTH', true, [testTraceEvent(3)])], async () => {
      throw new TypeError('network');
    });
    feed.start('txn_1', 'ASSESSING');
    await vi.waitFor(() => expect(feed.mode()).toBe('done'));
    expect(seqs(feed)).toEqual([1, 2, 3]);
    expect(api.timeline.mock.calls.map((c) => c[1])).toEqual([0, 1, 2]);
    const calls = api.timeline.mock.calls.length;
    await new Promise((r) => setTimeout(r, 30));
    expect(api.timeline.mock.calls.length).toBe(calls);
  });

  it.each([
    ['server error', () => new Response('nope', { status: 500 })],
    ['wrong content type', () => new Response('<html>', { status: 200, headers: { 'content-type': 'text/html' } })],
    ['no readable body', () => new Response(null, { status: 200, headers: { 'content-type': 'text/event-stream' } })],
  ])('falls back to polling on %s', async (_name, make) => {
    const { feed } = setup([snap('ASSESSING', false), snap('READY_FOR_AUTH', true, [testTraceEvent(1)])], async () => make());
    feed.start('txn_1', 'ASSESSING');
    await vi.waitFor(() => expect(feed.mode()).toBe('done'));
    expect(seqs(feed)).toEqual([1]);
  });
});

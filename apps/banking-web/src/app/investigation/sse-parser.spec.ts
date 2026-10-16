import { SseParser } from './sse-parser';

describe('SseParser', () => {
  it('parses a complete timeline frame', () => {
    const frames = new SseParser().push('event: timeline\nid: 3\ndata: {"seq":3}\n\n');
    expect(frames).toEqual([{ event: 'timeline', id: '3', data: '{"seq":3}' }]);
  });

  it('handles frames split at arbitrary chunk boundaries', () => {
    const text = 'event: timeline\nid: 1\ndata: {"seq":1}\n\nevent: timeline\nid: 2\ndata: {"seq":2}\n\n';
    for (let cut = 1; cut < text.length; cut++) {
      const p = new SseParser();
      const frames = [...p.push(text.slice(0, cut)), ...p.push(text.slice(cut))];
      expect(frames.map((f) => f.id)).toEqual(['1', '2']);
    }
  });

  it('handles one character at a time', () => {
    const p = new SseParser();
    const frames = [...'event: done\ndata: {}\n\n'].flatMap((c) => p.push(c));
    expect(frames).toEqual([{ event: 'done', id: null, data: '{}' }]);
  });

  it('ignores ": ping" keep-alives and comments', () => {
    const frames = new SseParser().push(': ping\n\n: ping\nevent: timeline\nid: 1\ndata: {}\n\n');
    expect(frames).toHaveLength(1);
    expect(frames[0].event).toBe('timeline');
  });

  it('supports CRLF, including a CR/LF pair split across chunks', () => {
    const p = new SseParser();
    const frames = [...p.push('event: timeline\r\nid: 7\r'), ...p.push('\ndata: {"a":1}\r\n\r'), ...p.push('\n')];
    expect(frames).toEqual([{ event: 'timeline', id: '7', data: '{"a":1}' }]);
  });

  it('joins multi-line data and strips one leading space', () => {
    const frames = new SseParser().push('data: a\ndata:  b\n\n');
    expect(frames[0].data).toBe('a\n b');
    expect(frames[0].event).toBe('message');
  });

  it('does not emit a partial frame until the blank line arrives', () => {
    const p = new SseParser();
    expect(p.push('event: timeline\nid: 1\ndata: {}')).toEqual([]);
    expect(p.push('\n\n')).toHaveLength(1);
  });
});

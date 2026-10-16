export interface SseFrame {
  event: string;
  id: string | null;
  data: string;
}

/** Incremental text/event-stream parser. Feed decoded text chunks; get completed frames back. */
export class SseParser {
  private buffer = '';
  private event = '';
  private id: string | null = null;
  private data: string[] = [];

  push(chunk: string): SseFrame[] {
    this.buffer += chunk;
    const frames: SseFrame[] = [];
    let start = 0;
    for (let i = 0; i < this.buffer.length; i++) {
      const ch = this.buffer[i];
      if (ch !== '\n' && ch !== '\r') continue;
      if (ch === '\r') {
        // A trailing CR may be the first half of CRLF that continues in the next chunk.
        if (i === this.buffer.length - 1) break;
        const line = this.buffer.slice(start, i);
        start = this.buffer[i + 1] === '\n' ? i + 2 : i + 1;
        if (this.buffer[i + 1] === '\n') i++;
        this.line(line, frames);
      } else {
        this.line(this.buffer.slice(start, i), frames);
        start = i + 1;
      }
    }
    this.buffer = this.buffer.slice(start);
    return frames;
  }

  private line(line: string, frames: SseFrame[]): void {
    if (line === '') {
      if (this.data.length || this.event) {
        frames.push({ event: this.event || 'message', id: this.id, data: this.data.join('\n') });
      }
      this.event = '';
      this.data = [];
      return;
    }
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') this.event = value;
    else if (field === 'data') this.data.push(value);
    else if (field === 'id') this.id = value;
  }
}

// Handles SSE chunk boundary splitting: accumulates lines, emits complete events
export interface SSEEvent {
    id?: string;
    event: string;
    data: string;
}

const MAX_BUFFER_SIZE = 64 * 1024; // 64 KB

export class SSEParser {
    private buffer = "";

    feed(chunk: string): SSEEvent[] {
        // Browsers may surface SSE payloads with CRLF separators; normalize them
        // before splitting so both `\n\n` and `\r\n\r\n` are handled identically.
        this.buffer = `${this.buffer}${chunk}`.replace(/\r\n?/g, "\n");
        if (this.buffer.length > MAX_BUFFER_SIZE) {
            this.buffer = "";
            throw new Error(
                `SSEParser: buffer limit exceeded (${MAX_BUFFER_SIZE} bytes) — missing \\n\\n separator`
            );
        }
        const events: SSEEvent[] = [];
        const parts = this.buffer.split("\n\n");
        // Last part may be incomplete — keep it in buffer
        this.buffer = parts.pop() ?? "";

        for (const part of parts) {
            const lines = part.split("\n");
            let eventType = "message";
            let eventId: string | undefined = undefined;
            const dataLines: string[] = [];
            for (const line of lines) {
                if (line.startsWith("event: ")) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith("id: ")) {
                    eventId = line.slice(4).trim();
                } else if (line.startsWith("data: ")) {
                    dataLines.push(line.slice(6));
                }
            }
            if (dataLines.length > 0) {
                events.push({ id: eventId, event: eventType, data: dataLines.join("\n") });
            }
        }
        return events;
    }
}

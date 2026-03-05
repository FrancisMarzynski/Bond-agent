// Handles SSE chunk boundary splitting: accumulates lines, emits complete events
export interface SSEEvent {
    event: string;
    data: string;
}

export class SSEParser {
    private buffer = "";

    feed(chunk: string): SSEEvent[] {
        this.buffer += chunk;
        const events: SSEEvent[] = [];
        const parts = this.buffer.split("\n\n");
        // Last part may be incomplete — keep it in buffer
        this.buffer = parts.pop() ?? "";

        for (const part of parts) {
            const lines = part.split("\n");
            let eventType = "message";
            const dataLines: string[] = [];
            for (const line of lines) {
                if (line.startsWith("event: ")) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith("data: ")) {
                    dataLines.push(line.slice(6));
                }
            }
            if (dataLines.length > 0) {
                events.push({ event: eventType, data: dataLines.join("\n") });
            }
        }
        return events;
    }
}

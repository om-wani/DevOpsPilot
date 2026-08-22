export type ChatEvent =
  | { type: "sources"; sources: string[] }
  | { type: "token"; text: string }
  | { type: "done"; usage: { prompt_tokens: number | null; completion_tokens: number | null } | null }
  | { type: "error"; error: string; message: string };

/**
 * Split a buffer into whole SSE frames, returning the leftover partial frame.
 *
 * A network chunk can end mid-frame, so anything after the last blank line has
 * to be carried into the next read. Splitting naively drops tokens.
 */
export function splitFrames(buffer: string): { frames: string[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  return { frames: parts.filter((p) => p.trim().length > 0), rest };
}

export function parseFrame(frame: string): ChatEvent | null {
  const line = frame.split("\n").find((l) => l.startsWith("data: "));
  if (!line) return null;
  try {
    return JSON.parse(line.slice("data: ".length)) as ChatEvent;
  } catch {
    return null;
  }
}

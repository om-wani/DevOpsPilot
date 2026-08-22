import { describe, expect, it } from "vitest";

import { parseFrame, splitFrames } from "../sse";

const frame = (payload: unknown) => `data: ${JSON.stringify(payload)}\n\n`;

describe("splitFrames", () => {
  it("returns whole frames and keeps nothing back when the buffer ends cleanly", () => {
    const buffer = frame({ type: "token", text: "a" }) + frame({ type: "token", text: "b" });
    const { frames, rest } = splitFrames(buffer);

    expect(frames).toHaveLength(2);
    expect(rest).toBe("");
  });

  it("carries a partial trailing frame into the next read", () => {
    const buffer = frame({ type: "token", text: "a" }) + 'data: {"type": "tok';
    const { frames, rest } = splitFrames(buffer);

    expect(frames).toHaveLength(1);
    expect(rest).toBe('data: {"type": "tok');
  });

  it("loses no tokens when a frame is split across two chunks", () => {
    const whole = frame({ type: "token", text: "hello" }) + frame({ type: "token", text: "world" });
    const cut = 20;

    const first = splitFrames(whole.slice(0, cut));
    const second = splitFrames(first.rest + whole.slice(cut));
    const events = [...first.frames, ...second.frames].map(parseFrame);

    expect(events.map((e) => (e as { text: string }).text)).toEqual(["hello", "world"]);
  });

  it("handles a buffer with no complete frame at all", () => {
    const { frames, rest } = splitFrames("data: {");
    expect(frames).toEqual([]);
    expect(rest).toBe("data: {");
  });

  it("ignores keep-alive blank lines", () => {
    const { frames } = splitFrames("\n\n" + frame({ type: "token", text: "a" }));
    expect(frames).toHaveLength(1);
  });
});

describe("parseFrame", () => {
  it("reads the event out of a frame", () => {
    expect(parseFrame('data: {"type":"token","text":"hi"}')).toEqual({
      type: "token",
      text: "hi",
    });
  });

  it("preserves newlines inside the payload", () => {
    const event = parseFrame(`data: ${JSON.stringify({ type: "token", text: "one\ntwo" })}`);
    expect((event as { text: string }).text).toBe("one\ntwo");
  });

  it("returns null for a frame with no data line", () => {
    expect(parseFrame(": keep-alive")).toBeNull();
  });

  it("returns null rather than throwing on malformed json", () => {
    expect(parseFrame('data: {"type": ')).toBeNull();
  });
});

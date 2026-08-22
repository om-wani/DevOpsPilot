import * as SDK from "azure-devops-extension-sdk";

import { ChatEvent, parseFrame, splitFrames } from "./sse";

export type { ChatEvent };

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "https://localhost:8000";

export interface AskOptions {
  question: string;
  workItemId?: number;
  conversationId?: string;
  signal?: AbortSignal;
}

/**
 * Stream an answer from the backend.
 *
 * EventSource cannot set an Authorization header, so this reads the SSE stream
 * off fetch's ReadableStream instead.
 */
export async function* ask(options: AskOptions): AsyncGenerator<ChatEvent> {
  const token = await SDK.getAccessToken();

  const response = await fetch(`${BACKEND_URL}/api/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      question: options.question,
      work_item_id: options.workItemId,
      conversation_id: options.conversationId,
    }),
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    let message = "The assistant is unavailable right now.";
    try {
      message = (await response.json()).message ?? message;
    } catch {
      // A non-JSON error body tells the user nothing useful; keep the default.
    }
    yield { type: "error", error: "request_failed", message };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const { frames, rest } = splitFrames(buffer);
    buffer = rest;

    for (const frame of frames) {
      const event = parseFrame(frame);
      if (event) yield event;
    }
  }
}

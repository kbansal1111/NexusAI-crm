import { getSession } from "next-auth/react";
import { apiClient } from "@/lib/api/client";
import { API_BASE_URL } from "@/lib/env";

// ── Types ────────────────────────────────────────────────────────────────────

export interface AssistantConversationMeta {
    id: string;
    title?: string;
    updated_at?: string;
    message_count: number;
}

export interface AssistantMessage {
    role: "user" | "assistant";
    content: string;
}

export interface AssistantStreamHandlers {
    /** Fired once with the (possibly new) conversation id. */
    onMeta?: (conversationId: string) => void;
    /** Fired when the model calls a tool (name only — for a status chip). */
    onTool?: (name: string) => void;
    /** Fired per streamed text token. */
    onToken: (text: string) => void;
    onDone?: () => void;
    onError?: (detail: string) => void;
}

// ── SSE chat stream ──────────────────────────────────────────────────────────
// axios can't stream response bodies in the browser, so the chat call uses raw
// fetch + ReadableStream. Auth mirrors the axios interceptor (NextAuth bearer).

export async function streamAssistantChat(
    message: string,
    conversationId: string | undefined,
    handlers: AssistantStreamHandlers,
    signal?: AbortSignal
): Promise<void> {
    const session = await getSession();
    const token = (session as any)?.accessToken as string | undefined;

    const res = await fetch(`${API_BASE_URL}api/v1/assistant/chat`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message, conversation_id: conversationId }),
        signal,
    });

    if (!res.ok || !res.body) {
        handlers.onError?.(
            res.status === 403
                ? "You don't have permission to use the assistant."
                : `Assistant request failed (${res.status}).`
        );
        return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const handleFrame = (frame: string) => {
        let event = "message";
        let data = "";
        for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) return;
        try {
            const payload = JSON.parse(data);
            if (event === "meta" && payload.conversation_id) handlers.onMeta?.(payload.conversation_id);
            else if (event === "tool" && payload.name) handlers.onTool?.(payload.name);
            else if (event === "token" && typeof payload.text === "string") handlers.onToken(payload.text);
            else if (event === "done") handlers.onDone?.();
            else if (event === "error") handlers.onError?.(payload.detail || "Assistant error.");
        } catch {
            // Malformed frame — skip rather than break the stream.
        }
    };

    // eslint-disable-next-line no-constant-condition
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE frames are separated by a blank line.
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
            handleFrame(buffer.slice(0, idx));
            buffer = buffer.slice(idx + 2);
        }
    }
    if (buffer.trim()) handleFrame(buffer);
}

// ── Conversation CRUD (plain axios) ──────────────────────────────────────────

export const assistantService = {
    listConversations: async (): Promise<AssistantConversationMeta[]> => {
        const res = await apiClient.get<AssistantConversationMeta[]>("/assistant/conversations");
        return res.data;
    },

    getConversation: async (
        id: string
    ): Promise<{ id: string; title?: string; messages: AssistantMessage[] }> => {
        const res = await apiClient.get(`/assistant/conversations/${id}`);
        return res.data;
    },

    deleteConversation: async (id: string): Promise<void> => {
        await apiClient.delete(`/assistant/conversations/${id}`);
    },
};

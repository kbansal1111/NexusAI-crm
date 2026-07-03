"use client";

import { useCallback, useRef, useState } from "react";
import {
    AssistantMessage,
    assistantService,
    streamAssistantChat,
} from "@/lib/api/services/assistant.service";

export interface ChatMessage extends AssistantMessage {
    /** Tool names the assistant used while producing this message (status chips). */
    tools?: string[];
    streaming?: boolean;
}

/**
 * Manages one assistant conversation: message state, SSE streaming, history.
 */
export function useAssistantChat() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [conversationId, setConversationId] = useState<string | undefined>();
    const [isStreaming, setIsStreaming] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const abortRef = useRef<AbortController | null>(null);

    const send = useCallback(
        async (text: string) => {
            const trimmed = text.trim();
            if (!trimmed || isStreaming) return;

            setError(null);
            setIsStreaming(true);
            setMessages((prev) => [
                ...prev,
                { role: "user", content: trimmed },
                { role: "assistant", content: "", tools: [], streaming: true },
            ]);

            const patchLast = (fn: (m: ChatMessage) => ChatMessage) =>
                setMessages((prev) => {
                    const next = [...prev];
                    next[next.length - 1] = fn(next[next.length - 1]);
                    return next;
                });

            const controller = new AbortController();
            abortRef.current = controller;
            try {
                await streamAssistantChat(
                    trimmed,
                    conversationId,
                    {
                        onMeta: (id) => setConversationId(id),
                        onTool: (name) =>
                            patchLast((m) => ({ ...m, tools: [...(m.tools || []), name] })),
                        onToken: (t) => patchLast((m) => ({ ...m, content: m.content + t })),
                        onError: (detail) => setError(detail),
                    },
                    controller.signal
                );
            } catch (e: any) {
                if (e?.name !== "AbortError") setError("Connection to the assistant failed.");
            } finally {
                patchLast((m) => ({ ...m, streaming: false }));
                setIsStreaming(false);
                abortRef.current = null;
            }
        },
        [conversationId, isStreaming]
    );

    const stop = useCallback(() => abortRef.current?.abort(), []);

    const loadConversation = useCallback(async (id: string) => {
        const data = await assistantService.getConversation(id);
        setConversationId(data.id);
        setMessages(data.messages.map((m) => ({ ...m })));
        setError(null);
    }, []);

    const newConversation = useCallback(() => {
        abortRef.current?.abort();
        setConversationId(undefined);
        setMessages([]);
        setError(null);
    }, []);

    return {
        messages,
        conversationId,
        isStreaming,
        error,
        send,
        stop,
        loadConversation,
        newConversation,
    };
}

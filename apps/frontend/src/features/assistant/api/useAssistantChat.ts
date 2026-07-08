"use client";

import { useCallback, useRef, useState } from "react";
import {
    AssistantMessage,
    assistantService,
    PendingAction,
    streamAssistantChat,
} from "@/lib/api/services/assistant.service";

export interface ChatMessage extends AssistantMessage {
    /** Tool names the assistant used while producing this message (status chips). */
    tools?: string[];
    /** Write proposals awaiting user Approve/Cancel (confirmation cards). */
    actions?: PendingAction[];
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
                { role: "assistant", content: "", tools: [], actions: [], streaming: true },
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
                        onConfirm: (actionId, summary) =>
                            patchLast((m) => ({
                                ...m,
                                actions: [
                                    ...(m.actions || []),
                                    { action_id: actionId, summary, state: "pending" },
                                ],
                            })),
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

    /** Approve or cancel a proposed write. Executes ONLY via this explicit call. */
    const resolveAction = useCallback(async (actionId: string, approve: boolean) => {
        const patchAction = (patch: Partial<import("@/lib/api/services/assistant.service").PendingAction>) =>
            setMessages((prev) =>
                prev.map((m) =>
                    m.actions?.some((a) => a.action_id === actionId)
                        ? {
                              ...m,
                              actions: m.actions!.map((a) =>
                                  a.action_id === actionId ? { ...a, ...patch } : a
                              ),
                          }
                        : m
                )
            );

        patchAction({ state: "executing" });
        try {
            if (approve) {
                const res = await assistantService.confirmAction(actionId);
                patchAction({
                    state: "executed",
                    resultMessage: res.result?.message || "Done.",
                });
            } else {
                await assistantService.rejectAction(actionId);
                patchAction({ state: "rejected", resultMessage: "Cancelled." });
            }
        } catch (e: any) {
            patchAction({
                state: "failed",
                resultMessage:
                    e?.response?.data?.detail || "Could not apply the change. Try again.",
            });
        }
    }, []);

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
        resolveAction,
        loadConversation,
        newConversation,
    };
}

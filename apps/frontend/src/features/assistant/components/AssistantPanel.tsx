"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Check, Loader2, Plus, Search, Send, Sparkles, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useAssistantChat } from "../api/useAssistantChat";

const TOOL_LABELS: Record<string, string> = {
    search_opportunities: "Searching opportunities",
    get_opportunity: "Reading opportunity",
    get_opportunity_financials: "Reading financials",
    list_opportunity_transactions: "Reading transactions",
    pipeline_summary: "Summarizing pipeline",
    resolve_picklist: "Looking up options",
    propose_update_opportunity: "Preparing an update",
    propose_create_task: "Preparing a task",
    propose_create_note: "Preparing a note",
    search_leads: "Searching leads",
    get_lead: "Reading lead",
    search_accounts: "Searching accounts",
    get_account: "Reading account",
};

const SUGGESTIONS = [
    "How is my pipeline looking by stage?",
    "Which deals are closing this month?",
    "Show my leads from this week",
    "Find accounts in Mumbai",
];

export function AssistantPanel() {
    const { messages, isStreaming, error, send, stop, resolveAction, newConversation } =
        useAssistantChat();
    const [input, setInput] = useState("");
    const [open, setOpen] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    // Keep the newest message in view while streaming.
    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    }, [messages]);

    const submit = () => {
        if (!input.trim() || isStreaming) return;
        void send(input);
        setInput("");
    };

    return (
        <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
                <Button
                    variant="ghost"
                    size="icon"
                    title="AI Assistant"
                    className="text-muted-foreground hover:text-foreground"
                >
                    <Sparkles className="h-5 w-5" />
                </Button>
            </SheetTrigger>
            <SheetContent className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
                <SheetHeader className="border-b border-border px-4 py-3">
                    <div className="flex items-center justify-between pr-8">
                        <div>
                            <SheetTitle className="flex items-center gap-2 text-base">
                                <Bot className="h-4 w-4 text-primary" /> Assistant
                            </SheetTitle>
                            <SheetDescription className="text-xs">
                                Ask about opportunities, leads &amp; accounts. Changes need your approval.
                            </SheetDescription>
                        </div>
                        <Button
                            variant="ghost"
                            size="icon"
                            title="New conversation"
                            onClick={newConversation}
                            className="h-8 w-8 text-muted-foreground"
                        >
                            <Plus className="h-4 w-4" />
                        </Button>
                    </div>
                </SheetHeader>

                {/* Messages */}
                <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
                    {messages.length === 0 && (
                        <div className="space-y-3 pt-8 text-center">
                            <Sparkles className="mx-auto h-8 w-8 text-primary/60" />
                            <p className="text-sm text-muted-foreground">
                                Ask anything about your opportunities, leads, or accounts.
                            </p>
                            <div className="space-y-1.5">
                                {SUGGESTIONS.map((s) => (
                                    <button
                                        key={s}
                                        onClick={() => void send(s)}
                                        className="block w-full rounded-md border border-border px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-muted"
                                    >
                                        {s}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {messages.map((m, i) => (
                        <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                            <div
                                className={
                                    m.role === "user"
                                        ? "max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3 py-2 text-sm text-white"
                                        : "max-w-[92%] rounded-2xl rounded-bl-sm bg-muted px-3 py-2 text-sm text-foreground"
                                }
                            >
                                {m.role === "assistant" && (m.tools?.length ?? 0) > 0 && (
                                    <div className="mb-1.5 flex flex-wrap gap-1">
                                        {m.tools!.map((t, j) => (
                                            <span
                                                key={j}
                                                className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary dark:text-primary"
                                            >
                                                <Search className="h-2.5 w-2.5" />
                                                {TOOL_LABELS[t] || t}
                                            </span>
                                        ))}
                                    </div>
                                )}
                                <div className="whitespace-pre-wrap break-words">
                                    {m.content}
                                    {m.streaming && !m.content && (
                                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                    )}
                                </div>

                                {/* Write-proposal confirmation cards */}
                                {(m.actions || []).map((a) => (
                                    <div
                                        key={a.action_id}
                                        className="mt-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5"
                                    >
                                        <p className="text-xs font-medium text-foreground">{a.summary}</p>
                                        {a.state === "pending" && (
                                            <div className="mt-2 flex gap-2">
                                                <Button
                                                    size="sm"
                                                    className="h-7 bg-emerald-600 px-3 text-xs hover:bg-emerald-700"
                                                    onClick={() => void resolveAction(a.action_id, true)}
                                                >
                                                    <Check className="mr-1 h-3 w-3" /> Approve
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="h-7 px-3 text-xs"
                                                    onClick={() => void resolveAction(a.action_id, false)}
                                                >
                                                    <X className="mr-1 h-3 w-3" /> Cancel
                                                </Button>
                                            </div>
                                        )}
                                        {a.state === "executing" && (
                                            <p className="mt-1.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                                                <Loader2 className="h-3 w-3 animate-spin" /> Applying…
                                            </p>
                                        )}
                                        {a.state === "executed" && (
                                            <p className="mt-1.5 flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                                                <Check className="h-3 w-3" /> {a.resultMessage || "Applied."}
                                            </p>
                                        )}
                                        {a.state === "rejected" && (
                                            <p className="mt-1.5 text-[11px] text-muted-foreground">Cancelled.</p>
                                        )}
                                        {a.state === "failed" && (
                                            <p className="mt-1.5 text-[11px] font-medium text-red-600 dark:text-red-400">
                                                {a.resultMessage || "Failed to apply."}
                                            </p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}

                    {error && (
                        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-300">
                            {error}
                        </p>
                    )}
                </div>

                {/* Composer */}
                <div className="border-t border-border p-3">
                    <div className="flex items-end gap-2">
                        <Textarea
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) {
                                    e.preventDefault();
                                    submit();
                                }
                            }}
                            placeholder="Ask about your opportunities…"
                            rows={1}
                            className="max-h-28 min-h-[38px] flex-1 resize-none text-sm"
                        />
                        {isStreaming ? (
                            <Button size="icon" variant="outline" onClick={stop} title="Stop">
                                <Square className="h-4 w-4" />
                            </Button>
                        ) : (
                            <Button size="icon" onClick={submit} disabled={!input.trim()} title="Send">
                                <Send className="h-4 w-4" />
                            </Button>
                        )}
                    </div>
                    <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
                        Answers come from your CRM data · changes apply only after you approve
                    </p>
                </div>
            </SheetContent>
        </Sheet>
    );
}

"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: string[];
  flags: string[];
  timestamp: Date;
  userId?: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Welcome to the ISA Regulations Assistant.\n\nI answer questions strictly based on the ISA exploitation regulations (ISBA/31/C/CRP.1/Rev.2) and UNCLOS Part XI. I will:\n• Cite specific regulation numbers in every answer\n• Flag unresolved [bracketed] provisions\n• Flag circular procedural dependencies\n• Refuse to speculate beyond the regulatory texts\n\nWhat would you like to know?",
      citations: [],
      flags: [],
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [userName, setUserName] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    if (!input.trim() || loading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      citations: [],
      flags: [],
      timestamp: new Date(),
      userId: userName || "Anonymous",
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg.content,
          thread_id: threadId,
          history: messages.slice(-6).map((m) => ({
            role: m.role,
            content: m.content,
          })),
          user_id: userName || "anonymous",
        }),
      });

      if (!res.ok) {
        throw new Error(`API error: ${res.status}`);
      }

      const data = await res.json();
      setThreadId(data.thread_id);

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.reply,
        citations: data.citations || [],
        flags: data.flags || [],
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            "⚠️ Unable to connect to the API. Please ensure the backend server is running (`uvicorn app.main:app` in the backend directory) and ANTHROPIC_API_KEY is set.",
          citations: [],
          flags: ["error"],
          timestamp: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 flex flex-col" style={{ height: "calc(100vh - 120px)" }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Regulations Assistant</h1>
          <p className="text-sm text-gray-500">
            Grounded in ISBA/31/C/CRP.1/Rev.2 + UNCLOS Part XI · No hallucination
          </p>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            placeholder="Your name / organisation"
            value={userName}
            onChange={(e) => setUserName(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 w-48"
          />
          {threadId && (
            <span className="text-xs text-gray-400 font-mono">
              Thread: {threadId.slice(0, 8)}
            </span>
          )}
        </div>
      </div>

      {/* Grounding notice */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-2 text-xs text-blue-800 mb-4 flex items-center gap-2">
        <span>🔒</span>
        <span>
          All answers are grounded exclusively in the regulatory corpus. Unresolved provisions are flagged. Set{" "}
          <code className="bg-blue-100 px-1 rounded">ANTHROPIC_API_KEY</code> in the backend to enable.
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div className={`max-w-2xl ${msg.role === "user" ? "items-end" : "items-start"} flex flex-col gap-1`}>
              {msg.userId && msg.role === "user" && (
                <span className="text-xs text-gray-400 mr-2">{msg.userId}</span>
              )}
              <div className={msg.role === "user" ? "chat-user" : "chat-assistant"}>
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                  {msg.content}
                </pre>
              </div>

              {/* Citations */}
              {msg.citations.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {msg.citations.map((c) => (
                    <span
                      key={c}
                      className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full font-mono"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              )}

              {/* Flags */}
              {msg.flags.length > 0 && (
                <div className="flex gap-2 mt-1">
                  {msg.flags.includes("unresolved") && (
                    <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full font-semibold">
                      ⚠️ Unresolved provisions flagged
                    </span>
                  )}
                  {msg.flags.includes("circular") && (
                    <span className="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded-full font-semibold">
                      🔄 Circular dependency detected
                    </span>
                  )}
                  {msg.flags.includes("out_of_scope") && (
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full font-semibold">
                      📋 Not in regulatory corpus
                    </span>
                  )}
                </div>
              )}

              <span className="text-xs text-gray-400">
                {msg.timestamp.toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="chat-assistant">
              <div className="flex gap-1 items-center h-5">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-3 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
          placeholder="Ask about a regulation, provision, or concept... (Enter to send, Shift+Enter for new line)"
          className="flex-1 border border-gray-200 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          rows={2}
        />
        <button
          onClick={sendMessage}
          disabled={!input.trim() || loading}
          className="bg-blue-900 text-white px-5 py-3 rounded-xl font-semibold text-sm hover:bg-blue-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  );
}

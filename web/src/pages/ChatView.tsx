import { useState } from "react";
import { Link } from "react-router-dom";
import { sendChat } from "../lib/api";
import type { ChatCitation, ChatMessage } from "../lib/types";
import { useRunContext } from "../lib/runContext";

interface Turn {
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
}

// The last one is deliberately outside any literature corpus: the refusal it gets is the
// trust argument for the whole system (docs/TESTING.md demo arc, step 6).
function suggestions(query: string | undefined): { label: string; text: string; refusal?: boolean }[] {
  return [
    { label: "Summarise", text: `What do the papers in this run find about ${query ?? "this topic"}?` },
    { label: "Disagreements", text: "Where do these papers disagree with each other, and why?" },
    { label: "Limitations", text: "What limitations or open problems do the authors report?" },
    { label: "Test the refusal", text: "Who won the 2018 FIFA World Cup?", refusal: true },
  ];
}

export default function ChatView() {
  const { runId, run } = useRunContext();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function onSend(e: React.FormEvent) {
    e.preventDefault();
    await ask(input.trim());
  }

  async function ask(message: string) {
    if (!message || sending) return;
    setInput("");
    const history: ChatMessage[] = turns.map((t) => ({ role: t.role, content: t.content }));
    setTurns((prev) => [...prev, { role: "user", content: message }]);
    setSending(true);
    try {
      const res = await sendChat(runId, message, history);
      setTurns((prev) => [...prev, { role: "assistant", content: res.answer, citations: res.citations }]);
    } catch (err) {
      setTurns((prev) => [...prev, { role: "assistant", content: `Error: ${String(err)}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-6 py-6">
      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {turns.length === 0 && (
          <div>
            <p className="text-sm text-ink-500">
              Ask about what ATLAS read in this run. Answers are grounded in retrieved claims only —
              ask something unrelated and it will say so, not guess.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {suggestions(run?.query).map((s) => (
                <button
                  key={s.label}
                  onClick={() => ask(s.text)}
                  title={s.text}
                  className={`rounded-full border px-3 py-1.5 text-xs ${
                    s.refusal
                      ? "border-amber-400/40 text-amber-200 hover:bg-amber-400/10"
                      : "border-ink-700 text-ink-300 hover:bg-ink-800"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) => {
          // the refusal is decided by retrieval, before any LLM call (ADR-014) — show it as such
          const refused = t.role === "assistant" && !t.citations?.length && /did not read anything/i.test(t.content);
          return (
          <div key={i} className={t.role === "user" ? "text-right" : ""}>
            {refused && (
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-300">
                Refused — nothing ATLAS read addresses this
              </div>
            )}
            <div
              className={`inline-block max-w-[85%] rounded-xl px-4 py-2 text-left text-sm ${
                t.role === "user"
                  ? "bg-accent-600/30 text-accent-50"
                  : refused
                    ? "border border-amber-400/40 bg-amber-400/10 text-amber-100"
                    : "bg-ink-800/60 text-ink-100"
              }`}
            >
              {t.content}
            </div>
            {t.citations && t.citations.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {t.citations.map((c) => (
                  <Link
                    key={c.paper_id}
                    to={`/runs/${runId}/paper/${encodeURIComponent(c.paper_id)}`}
                    title={c.quote ?? ""}
                    className="rounded-full bg-ink-800 px-2 py-0.5 text-xs text-accent-300 hover:bg-ink-700"
                  >
                    {c.title.length > 35 ? `${c.title.slice(0, 35)}…` : c.title}
                  </Link>
                ))}
              </div>
            )}
          </div>
          );
        })}
        {sending && <p className="text-sm text-ink-500">Searching what ATLAS read…</p>}
      </div>

      <form onSubmit={onSend} className="flex gap-2 border-t border-ink-800 pt-4">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this run's papers…"
          className="flex-1 rounded-lg border border-ink-700 bg-ink-950 px-3 py-2 text-sm outline-none focus:border-accent-500"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-ink-950 disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </div>
  );
}

"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Spinner } from "@/components/Spinner";

// Requests go to the Next.js proxy route (/api/copilot) to avoid CORS.
// The proxy reads NEXT_PUBLIC_API_BASE server-side to reach the backend.

interface CopilotRunResponse {
  report_markdown: string;
  display_title: string;
  pubmed_queries?: unknown;
  articles?: unknown;
  literature_summaries?: unknown;
  analysis_plan?: unknown;
  rerank_debug?: unknown;
}

type HtmlToPdfInstance = {
  set(opts: Record<string, unknown>): HtmlToPdfInstance;
  from(el: HTMLElement): HtmlToPdfInstance;
  save(): Promise<void>;
};
type HtmlToPdf = () => HtmlToPdfInstance;

const STATUS_MESSAGES = [
  "Translating query…",
  "Searching PubMed…",
  "Re-ranking articles…",
  "Summarising literature…",
  "Generating analysis plan…",
];

export default function Home() {
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState("");
  const [includeDebug, setIncludeDebug] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CopilotRunResponse | null>(null);
  const [statusIdx, setStatusIdx] = useState(0);

  // Cycle status messages while loading
  useEffect(() => {
    if (!loading) return;
    setStatusIdx(0);
    const id = setInterval(() => {
      setStatusIdx((i) => (i + 1) % STATUS_MESSAGES.length);
    }, 5000);
    return () => clearInterval(id);
  }, [loading]);

  async function handleRun() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/copilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          context: context.trim() || undefined,
          retmax: 6,
          include_debug: includeDebug,
        }),
      });
      if (!res.ok) {
        setError(await res.text());
        return;
      }
      setResult(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleExportPdf() {
    if (!result) return;
    const el = document.getElementById("report-pdf-target");
    if (!el) return;
    const html2pdf = (
      (await import("html2pdf.js")).default as unknown as HtmlToPdf
    );
    const filename =
      (result.display_title || "research-report")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .slice(0, 60) + ".pdf";
    html2pdf()
      .set({
        margin: [12, 14],
        filename,
        image: { type: "jpeg", quality: 0.97 },
        html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
        jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
      })
      .from(el)
      .save();
  }

  const debugPayload = result
    ? {
        pubmed_queries: result.pubmed_queries,
        articles: result.articles,
        literature_summaries: result.literature_summaries,
        analysis_plan: result.analysis_plan,
        rerank_debug: result.rerank_debug,
      }
    : null;

  const hasDebug =
    debugPayload &&
    Object.values(debugPayload).some((v) => v !== undefined);

  return (
    <>
      <main className="min-h-screen py-10 px-4 relative z-10">
        <div className="max-w-7xl mx-auto flex flex-col gap-8">

          {/* Header */}
          <header className="flex flex-col gap-1.5">
            <h1 className="text-3xl font-bold tracking-tight">
              <span className="text-slate-400">✦ </span>
              <span className="text-cyan-400">AI</span>
              <span className="text-slate-100"> Research Copilot</span>
            </h1>
            <p className="text-slate-500 text-sm max-w-lg">
              Enter an epidemiological research question to generate a structured
              analysis plan, backed by PubMed literature.
            </p>
          </header>

          {/* Two-column layout */}
          <div className="flex flex-col lg:flex-row gap-5 lg:items-start">

            {/* ── Left: Input panel ── */}
            <section
              className="
                lg:w-[38%] shrink-0
                bg-white/[0.04] backdrop-blur-md border border-white/[0.08]
                rounded-2xl p-6 flex flex-col gap-5
              "
            >
              {/* Research Question */}
              <div className="flex flex-col gap-1.5">
                <label htmlFor="question" className="text-xs font-medium text-slate-400 uppercase tracking-widest">
                  Research Question <span className="text-cyan-500 normal-case tracking-normal">*</span>
                </label>
                <textarea
                  id="question"
                  rows={5}
                  placeholder="e.g. Does statin use reduce all-cause mortality in elderly patients with type 2 diabetes?"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  className="
                    w-full rounded-xl border border-white/[0.10] bg-white/[0.05]
                    px-3 py-2.5 text-sm text-slate-200 placeholder:text-slate-600
                    focus:outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/30
                    resize-y transition-colors
                  "
                />
              </div>

              {/* Context */}
              <div className="flex flex-col gap-1.5">
                <label htmlFor="context" className="text-xs font-medium text-slate-400 uppercase tracking-widest">
                  Context <span className="text-slate-600 normal-case tracking-normal font-normal">(optional)</span>
                </label>
                <textarea
                  id="context"
                  rows={3}
                  placeholder="e.g. Retrospective cohort using EHR data, adults aged 65+"
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  className="
                    w-full rounded-xl border border-white/[0.10] bg-white/[0.05]
                    px-3 py-2.5 text-sm text-slate-200 placeholder:text-slate-600
                    focus:outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/30
                    resize-y transition-colors
                  "
                />
              </div>

              {/* Debug checkbox */}
              <label className="flex items-center gap-2.5 cursor-pointer w-fit group">
                <input
                  type="checkbox"
                  checked={includeDebug}
                  onChange={(e) => setIncludeDebug(e.target.checked)}
                  className="w-4 h-4 rounded border-white/20 accent-cyan-400"
                />
                <span className="text-sm text-slate-400 group-hover:text-slate-300 transition-colors">
                  Include debug output
                </span>
              </label>

              {/* Run button */}
              <button
                onClick={handleRun}
                disabled={!question.trim() || loading}
                className="
                  relative w-full rounded-xl py-2.5 text-sm font-semibold text-white
                  bg-gradient-to-r from-cyan-500 to-purple-500
                  shadow-[0_0_18px_rgba(0,229,255,0.25)]
                  hover:shadow-[0_0_28px_rgba(0,229,255,0.45)]
                  disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none
                  transition-all duration-200
                "
              >
                {loading ? "Running…" : "Run Analysis"}
              </button>

              {/* Loading state (inside input panel on mobile, visible here) */}
              {loading && (
                <div className="flex items-center gap-3 text-sm text-slate-400 py-1">
                  <Spinner size={18} />
                  <span className="transition-all">{STATUS_MESSAGES[statusIdx]}</span>
                </div>
              )}

              {/* Error state */}
              {error && (
                <div className="rounded-xl border border-red-500/30 bg-red-950/20 p-4 flex flex-col gap-1.5">
                  <p className="text-sm font-semibold text-red-400">⚠ Request failed</p>
                  <pre className="text-xs text-red-300/70 font-mono whitespace-pre-wrap break-all leading-relaxed">
                    {error}
                  </pre>
                </div>
              )}
            </section>

            {/* ── Right: Report panel ── */}
            <section
              className="
                flex-1 min-w-0
                bg-white/[0.04] backdrop-blur-md border border-white/[0.08]
                rounded-2xl p-6 flex flex-col gap-4
              "
            >
              {/* Empty state */}
              {!result && !loading && !error && (
                <div className="flex flex-col items-center justify-center min-h-64 gap-3 text-slate-700">
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                    <rect x="8" y="8" width="32" height="32" rx="4" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 3" />
                    <line x1="16" y1="18" x2="32" y2="18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    <line x1="16" y1="24" x2="28" y2="24" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    <line x1="16" y1="30" x2="24" y2="30" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  <p className="text-sm">Your analysis report will appear here</p>
                </div>
              )}

              {/* Loading placeholder in report panel */}
              {loading && (
                <div className="flex flex-col items-center justify-center min-h-64 gap-4 text-slate-500">
                  <Spinner size={36} />
                  <div className="text-center">
                    <p className="text-sm font-medium text-slate-400">{STATUS_MESSAGES[statusIdx]}</p>
                    <p className="text-xs text-slate-600 mt-1">This may take 20–40 seconds</p>
                  </div>
                </div>
              )}

              {/* Report result */}
              {result && (
                <div className="flex flex-col gap-4">
                  {/* Toolbar */}
                  <div className="flex items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
                    <p className="text-xs text-slate-500 truncate">{result.display_title}</p>
                    <button
                      onClick={handleExportPdf}
                      className="
                        shrink-0 flex items-center gap-1.5 rounded-lg border border-cyan-500/30
                        px-3 py-1.5 text-xs text-cyan-400 font-medium
                        hover:bg-cyan-500/10 hover:border-cyan-500/50
                        transition-colors duration-150
                      "
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <path d="M8 2v9M4 8l4 4 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M2 13h12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                      </svg>
                      Export PDF
                    </button>
                  </div>

                  {/* Markdown report */}
                  <div
                    className="
                      text-sm leading-relaxed
                      [&_h1]:text-xl [&_h1]:font-bold [&_h1]:text-cyan-300 [&_h1]:mb-4 [&_h1]:mt-0
                      [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-slate-200 [&_h2]:mt-7 [&_h2]:mb-2
                      [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-slate-300 [&_h3]:mt-4 [&_h3]:mb-1.5
                      [&_p]:text-slate-300 [&_p]:leading-relaxed [&_p]:my-2
                      [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2 [&_ul]:text-slate-300
                      [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2 [&_ol]:text-slate-300
                      [&_li]:my-0.5 [&_li]:leading-relaxed
                      [&_strong]:text-slate-100 [&_strong]:font-semibold
                      [&_em]:italic [&_em]:text-slate-400
                      [&_code]:bg-slate-800 [&_code]:text-cyan-300 [&_code]:rounded [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-xs [&_code]:font-mono
                      [&_pre]:bg-slate-900 [&_pre]:rounded-xl [&_pre]:p-4 [&_pre]:text-xs [&_pre]:overflow-x-auto [&_pre]:border [&_pre]:border-white/[0.06] [&_pre]:my-3
                      [&_blockquote]:border-l-2 [&_blockquote]:border-cyan-500/40 [&_blockquote]:pl-4 [&_blockquote]:text-slate-400 [&_blockquote]:italic [&_blockquote]:my-3
                      [&_table]:w-full [&_table]:border-collapse [&_table]:my-4 [&_table]:text-xs
                      [&_th]:text-left [&_th]:border [&_th]:border-white/[0.08] [&_th]:bg-white/[0.04] [&_th]:px-3 [&_th]:py-2 [&_th]:text-slate-300 [&_th]:font-semibold
                      [&_td]:border [&_td]:border-white/[0.06] [&_td]:px-3 [&_td]:py-2 [&_td]:text-slate-400
                      [&_hr]:border-white/[0.08] [&_hr]:my-6
                      [&_a]:text-cyan-400 [&_a]:underline [&_a]:underline-offset-2
                    "
                  >
                    <ReactMarkdown>{result.report_markdown}</ReactMarkdown>
                  </div>

                  {/* Debug collapsible */}
                  {includeDebug && hasDebug && (
                    <details className="mt-2 border border-white/[0.08] rounded-xl overflow-hidden">
                      <summary className="px-5 py-3 text-xs font-medium text-purple-400 cursor-pointer select-none hover:bg-white/[0.03] transition-colors">
                        ⬡ Debug JSON
                      </summary>
                      <pre className="px-5 py-4 text-xs text-green-400 font-mono overflow-x-auto bg-black/30 border-t border-white/[0.05] whitespace-pre-wrap max-h-96 overflow-y-auto leading-relaxed">
                        {JSON.stringify(debugPayload, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </section>
          </div>
        </div>
      </main>

      {/* Hidden light-theme div for PDF export — off-screen, not visible to user */}
      {result && (
        <div
          id="report-pdf-target"
          aria-hidden="true"
          style={{
            position: "absolute",
            left: "-9999px",
            top: 0,
            width: "720px",
            background: "#ffffff",
            color: "#111111",
            fontFamily: "Georgia, 'Times New Roman', serif",
            fontSize: "13px",
            lineHeight: 1.65,
            padding: "32px 40px",
          }}
        >
          <ReactMarkdown>{result.report_markdown}</ReactMarkdown>
        </div>
      )}
    </>
  );
}

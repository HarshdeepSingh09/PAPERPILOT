import React, { useState } from 'react';
import {
  BookOpen,
  Sparkles,
  Bookmark,
  CheckCircle2,
  Users,
  FlaskConical,
  Send,
} from 'lucide-react';

type PreviewMode = 'chat' | 'summary' | 'intelligence';

export const HeroProductPreview: React.FC = () => {
  const [mode, setMode] = useState<PreviewMode>('chat');

  return (
    <div className="relative rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl shadow-slate-900/10 dark:shadow-black/50 overflow-hidden transition-colors duration-200">
      {/* Window Chrome */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-900/95">
        <div className="flex items-center space-x-2">
          <div className="flex space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-400/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/80" />
          </div>
          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 ml-2 hidden sm:inline">
            paperpilot.workspace / app
          </span>
        </div>

        {/* Interactive Mode Switcher */}
        <div className="flex items-center space-x-1 bg-slate-200/70 dark:bg-slate-800 p-0.5 rounded-lg text-[11px] font-medium">
          {[
            { id: 'chat', label: 'RAG Chat' },
            { id: 'summary', label: 'Summary' },
            { id: 'intelligence', label: 'Adaptive View' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setMode(tab.id as PreviewMode)}
              className={`px-2.5 py-1 rounded-md transition-all ${
                mode === tab.id
                  ? 'bg-white dark:bg-slate-700 text-brand-700 dark:text-brand-300 shadow-xs font-semibold'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Split Workspace Preview */}
      <div className="grid grid-cols-1 md:grid-cols-12 min-h-[340px]">
        {/* Left Library Rail */}
        <div className="hidden md:flex md:col-span-4 flex-col border-r border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 p-3 space-y-2">
          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 px-1">
            Library
          </div>

          <div className="p-2.5 rounded-xl bg-brand-50 dark:bg-brand-950/60 border border-brand-200 dark:border-brand-800/70">
            <div className="flex items-center space-x-2">
              <div className="p-1.5 rounded-lg bg-brand-600 text-white">
                <BookOpen className="w-3.5 h-3.5" />
              </div>
              <div className="min-w-0">
                <div className="text-[11px] font-semibold text-slate-800 dark:text-slate-100 truncate">
                  Chemistry_Chapter_1.pdf
                </div>
                <div className="flex items-center space-x-1 mt-0.5">
                  <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-white/80 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                    PDF
                  </span>
                  <span className="text-[9px] font-semibold text-brand-700 dark:text-brand-300">
                    Educational
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="p-2.5 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900/70">
            <div className="flex items-center space-x-2">
              <div className="p-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
                <Users className="w-3.5 h-3.5" />
              </div>
              <div className="min-w-0">
                <div className="text-[11px] font-semibold text-slate-700 dark:text-slate-200 truncate">
                  Product_Sync_Notes.docx
                </div>
                <div className="flex items-center space-x-1 mt-0.5">
                  <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                    DOCX
                  </span>
                  <span className="text-[9px] font-semibold text-emerald-700 dark:text-emerald-300">
                    Meeting Notes
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="p-2.5 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900/70">
            <div className="flex items-center space-x-2">
              <div className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300">
                <FlaskConical className="w-3.5 h-3.5" />
              </div>
              <div className="min-w-0">
                <div className="text-[11px] font-semibold text-slate-700 dark:text-slate-200 truncate">
                  Retrieval_Study_2026.pdf
                </div>
                <div className="flex items-center space-x-1 mt-0.5">
                  <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                    PDF
                  </span>
                  <span className="text-[9px] font-semibold text-indigo-700 dark:text-indigo-300">
                    Research Paper
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Interactive Output Area */}
        <div className="md:col-span-8 flex flex-col justify-between p-4 bg-white dark:bg-slate-900">
          {mode === 'chat' && (
            <>
              <div className="space-y-3">
                <div className="flex justify-end">
                  <div className="bg-brand-600 text-white text-xs px-3.5 py-2 rounded-2xl rounded-tr-none max-w-[85%] shadow-xs">
                    What happens when calcium oxide reacts with water?
                  </div>
                </div>

                <div className="flex items-start space-x-2.5">
                  <div className="w-7 h-7 rounded-lg bg-brand-600 text-white flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Sparkles className="w-3.5 h-3.5" />
                  </div>
                  <div className="bg-slate-100 dark:bg-slate-800/90 border border-slate-200/70 dark:border-slate-700 rounded-2xl rounded-tl-none p-3 text-xs text-slate-700 dark:text-slate-200 space-y-2">
                    <p className="leading-relaxed">
                      Calcium oxide (quicklime) reacts vigorously with water in an exothermic combination reaction to form slaked lime:
                    </p>
                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-1.5 font-mono text-[11px] text-center text-slate-800 dark:text-indigo-300">
                      CaO (s) + H₂O (l) → Ca(OH)₂ (aq) + Heat
                    </div>
                    <div className="flex items-center space-x-1.5 pt-1 border-t border-slate-200 dark:border-slate-700">
                      <Bookmark className="w-3 h-3 text-brand-600 dark:text-brand-400" />
                      <span className="px-2 py-0.5 rounded bg-brand-100 dark:bg-brand-950 text-brand-800 dark:text-brand-300 text-[10px] font-semibold">
                        Page 6
                      </span>
                      <span className="px-2 py-0.5 rounded bg-brand-100 dark:bg-brand-950 text-brand-800 dark:text-brand-300 text-[10px] font-semibold">
                        Page 7
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800 flex items-center space-x-2">
                <div className="flex-1 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-[11px] text-slate-400">
                  Ask a question grounded in your document...
                </div>
                <div className="p-2 rounded-xl bg-brand-600 text-white">
                  <Send className="w-3.5 h-3.5" />
                </div>
              </div>
            </>
          )}

          {mode === 'summary' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-brand-700 dark:text-brand-300 bg-brand-50 dark:bg-brand-950 px-2 py-0.5 rounded border border-brand-200 dark:border-brand-800">
                  Structured AI Summary
                </span>
                <span className="text-[10px] text-emerald-700 dark:text-emerald-300 flex items-center space-x-1 font-medium">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>7 Sections Cached</span>
                </span>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                <div className="text-xs font-bold text-slate-800 dark:text-slate-100 mb-1">Executive Overview</div>
                <p className="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">
                  Covers indicators of chemical reactions, Law of Conservation of Mass, equation balancing, and five core reaction types across pages 1–16.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                  <div className="text-[10px] font-bold text-indigo-700 dark:text-indigo-300">Key Takeaways</div>
                  <p className="text-[11px] text-slate-600 dark:text-slate-300 mt-1">
                    Balanced equations preserve atom counts on both sides (Page 3).
                  </p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                  <div className="text-[10px] font-bold text-emerald-700 dark:text-emerald-300">Page References</div>
                  <p className="text-[11px] text-slate-600 dark:text-slate-300 mt-1">
                    Verified concept & equation citations mapped to source pages.
                  </p>
                </div>
              </div>
            </div>
          )}

          {mode === 'intelligence' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950 px-2 py-0.5 rounded border border-emerald-200 dark:border-emerald-800">
                  Category: Meeting Notes (DOCX)
                </span>
                <span className="text-[10px] text-slate-500 dark:text-slate-400">Section citations</span>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                <div className="text-xs font-bold text-slate-800 dark:text-slate-100 mb-1">Important Decisions</div>
                <p className="text-[11px] text-slate-600 dark:text-slate-300">
                  Approved schema freeze and migration checklist timeline (Section 2).
                </p>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                <div className="text-xs font-bold text-slate-800 dark:text-slate-100 mb-1.5">
                  Explicitly Assigned Action Items
                </div>
                <div className="flex items-center justify-between text-[11px] py-1 border-b border-slate-200/70 dark:border-slate-700">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">Jordan Lee</span>
                  <span className="text-slate-500 dark:text-slate-400">Verify regression suite • Section 3</span>
                </div>
                <div className="flex items-center justify-between text-[11px] pt-1">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">Alex Patel</span>
                  <span className="text-slate-500 dark:text-slate-400">Finalize deployment notes • Section 3</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

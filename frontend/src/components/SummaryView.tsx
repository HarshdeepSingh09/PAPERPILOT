import React, { useState, useEffect } from 'react';
import {
  BookOpen,
  CheckCircle,
  Sparkles,
  Loader2,
  RefreshCw,
  Sigma,
  FileText,
  Lightbulb,
  Bookmark,
  ExternalLink,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { DocumentItem, DocumentSummary } from '../types';
import { studyApi } from '../api/client';

interface SummaryViewProps {
  document: DocumentItem;
}

export const SummaryView: React.FC<SummaryViewProps> = ({ document }) => {
  const [summary, setSummary] = useState<DocumentSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load existing summary automatically when document changes
  useEffect(() => {
    let isMounted = true;
    const fetchExistingSummary = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await studyApi.getSummary(document.id);
        if (isMounted) setSummary(data);
      } catch (err: any) {
        // If not generated yet (404), leave summary as null so user can trigger it
        if (isMounted) setSummary(null);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchExistingSummary();
    return () => {
      isMounted = false;
    };
  }, [document.id]);

  const handleGenerateSummary = async (force = false) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await studyApi.generateSummary(document.id, 'comprehensive', force);
      setSummary(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to generate summary.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 md:p-8 max-w-5xl mx-auto w-full">
      {/* Header Banner */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm mb-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs uppercase tracking-wider font-semibold text-brand-600 bg-brand-50 px-2.5 py-1 rounded-md border border-brand-200">
                AI Document Summary
              </span>
              {summary && (
                <span className="text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200 flex items-center space-x-1">
                  <CheckCircle className="w-3 h-3" />
                  <span>Synthesized & Cached</span>
                </span>
              )}
            </div>
            <h2 className="text-xl font-bold text-slate-800 mt-2">
              {summary?.title || document.original_filename}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Document: {document.original_filename} • {document.total_pages} Pages • Stored in SQLite
            </p>
          </div>

          <button
            onClick={() => handleGenerateSummary(!!summary)}
            disabled={isLoading || document.status !== 'ready'}
            title={document.status !== 'ready' ? 'Document is being processed' : undefined}
            className="flex items-center justify-center space-x-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Synthesizing...</span>
              </>
            ) : summary ? (
              <>
                <RefreshCw className="w-4 h-4" />
                <span>Regenerate Summary</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>Generate AI Summary</span>
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 mb-6 flex items-start space-x-2">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {isLoading && !summary ? (
        <div className="text-center py-20 bg-white border border-slate-200 rounded-2xl p-8">
          <Loader2 className="w-10 h-10 text-brand-600 animate-spin mx-auto mb-4" />
          <h3 className="text-sm font-bold text-slate-800">Synthesizing Document Summary</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            Reading all extracted chunks across {document.total_pages} pages, structuring formulas and key takeaways...
          </p>
        </div>
      ) : summary ? (
        <div className="space-y-6">
          {/* Section 1: Executive Overview */}
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2 mb-3">
              <BookOpen className="w-4 h-4 text-brand-600" />
              <span>1. Executive Overview</span>
            </h3>
            <p className="text-xs leading-relaxed text-slate-700 bg-slate-50 p-4 rounded-xl border border-slate-100">
              {summary.executive_overview || summary.overview}
            </p>
          </div>

          {/* Section 2: Key Takeaways */}
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2 mb-4">
              <CheckCircle className="w-4 h-4 text-emerald-600" />
              <span>2. Key Takeaways & Core Findings</span>
            </h3>
            <div className="grid grid-cols-1 gap-2.5">
              {summary.key_takeaways.map((takeaway, idx) => (
                <div
                  key={idx}
                  className="flex items-start space-x-3 p-3.5 bg-slate-50 hover:bg-slate-100/70 rounded-xl border border-slate-100 text-xs text-slate-700 transition-colors"
                >
                  <span className="flex-shrink-0 w-6 h-6 rounded-lg bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold text-[11px]">
                    {idx + 1}
                  </span>
                  <span className="leading-relaxed mt-0.5">{takeaway}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Section 3: Important Concepts */}
          {summary.important_concepts && summary.important_concepts.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2 mb-4">
                <Lightbulb className="w-4 h-4 text-amber-500" />
                <span>3. Important Concepts & Terminology</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {summary.important_concepts.map((concept, idx) => (
                  <div
                    key={idx}
                    className="p-4 bg-slate-50 rounded-xl border border-slate-100 flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <h4 className="text-xs font-bold text-slate-800">{concept.term}</h4>
                        {concept.source_page && (
                          <span className="text-[10px] font-semibold text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                            Page {concept.source_page}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-600 leading-relaxed">{concept.definition}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section 4: Formulas and Equations */}
          {summary.formulas_equations && summary.formulas_equations.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2 mb-4">
                <Sigma className="w-4 h-4 text-indigo-600" />
                <span>4. Important Formulas and Equations</span>
              </h3>
              <div className="grid grid-cols-1 gap-3.5">
                {summary.formulas_equations.map((eq, idx) => (
                  <div
                    key={idx}
                    className="p-4 bg-slate-50 rounded-xl border border-slate-100 overflow-x-auto"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-indigo-900">{eq.name}</span>
                      {eq.source_page && (
                        <span className="text-[10px] font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                          Page {eq.source_page}
                        </span>
                      )}
                    </div>
                    <div className="py-2 text-center text-slate-800 text-sm overflow-x-auto">
                      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {eq.equation_latex}
                      </ReactMarkdown>
                    </div>
                    <p className="text-xs text-slate-600 mt-2 italic">{eq.explanation}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section 5: Chapter-wise Summary */}
          {summary.chapter_summaries && summary.chapter_summaries.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2 mb-4">
                <FileText className="w-4 h-4 text-brand-600" />
                <span>5. Chapter & Section Breakdown</span>
              </h3>
              <div className="space-y-3.5">
                {summary.chapter_summaries.map((ch, idx) => (
                  <div key={idx} className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <div className="flex items-center justify-between mb-1.5">
                      <h4 className="text-xs font-bold text-slate-800">{ch.chapter_title}</h4>
                      {ch.source_page && (
                        <span className="text-[10px] text-slate-500 font-medium">Page {ch.source_page}</span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed mb-2">{ch.summary}</p>
                    {ch.key_points && ch.key_points.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-2 border-t border-slate-200/60">
                        {ch.key_points.map((pt, pIdx) => (
                          <span
                            key={pIdx}
                            className="text-[10px] font-medium text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200"
                          >
                            • {pt}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section 6: Important Facts */}
          {summary.important_facts && summary.important_facts.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2 mb-4">
                <Bookmark className="w-4 h-4 text-rose-500" />
                <span>6. Important Facts & Practical Observations</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {summary.important_facts.map((item, idx) => (
                  <div key={idx} className="p-3.5 bg-slate-50 rounded-xl border border-slate-100 flex flex-col justify-between">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                        {item.category || 'Fact'}
                      </span>
                      {item.source_page && (
                        <span className="text-[10px] text-slate-400">Page {item.source_page}</span>
                      )}
                    </div>
                    <div className="text-xs text-slate-700 leading-relaxed mt-1">
                      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {item.fact}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section 7: Page References */}
          {summary.page_references && summary.page_references.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2 mb-4">
                <ExternalLink className="w-4 h-4 text-slate-600" />
                <span>7. Verified Page References</span>
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
                {summary.page_references.map((ref, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-left"
                  >
                    <div className="text-xs font-bold text-brand-700">Page {ref.page}</div>
                    <div className="text-[11px] font-medium text-slate-700 truncate">{ref.topic}</div>
                    {ref.snippet && (
                      <div className="text-[10px] text-slate-400 truncate mt-0.5">{ref.snippet}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-20 bg-white border border-dashed border-slate-200 rounded-2xl p-8">
          <BookOpen className="w-12 h-12 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800">No summary generated yet</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            Click 'Generate AI Summary' above to synthesize all 7 core sections across {document.total_pages} pages.
          </p>
        </div>
      )}
    </div>
  );
};

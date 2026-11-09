import React, { useState, useEffect } from 'react';
import {
  BookOpen,
  CheckCircle,
  Loader2,
  RefreshCw,
  Printer,
  Sigma,
  Bookmark,
  Lightbulb,
  Split,
  HelpCircle,
  Zap,
  FlaskConical,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { DocumentItem, RevisionNotesData } from '../types';
import { studyApi } from '../api/client';

interface RevisionNotesViewProps {
  document: DocumentItem;
}

export const RevisionNotesView: React.FC<RevisionNotesViewProps> = ({ document }) => {
  const [notes, setNotes] = useState<RevisionNotesData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<string>('overview');

  // Load existing revision notes automatically when document changes
  useEffect(() => {
    let isMounted = true;
    const fetchExistingNotes = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await studyApi.getRevisionNotes(document.id);
        if (isMounted) setNotes(data);
      } catch (err: any) {
        // If not found, leave as null so user can generate
        if (isMounted) setNotes(null);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchExistingNotes();
    return () => {
      isMounted = false;
    };
  }, [document.id]);

  const handleGenerateNotes = async (force = false) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await studyApi.generateRevisionNotes(document.id, force);
      setNotes(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to generate revision notes.');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const scrollToSection = (id: string) => {
    setActiveSection(id);
    const element = window.document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 md:p-8 max-w-5xl mx-auto w-full print:p-0 print:max-w-none">
      {/* Print styles */}
      <style>{`
        @media print {
          body {
            background-color: white !important;
            color: black !important;
          }
          header, aside, .no-print {
            display: none !important;
          }
          .print-full {
            width: 100% !important;
            max-width: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
          }
          .break-inside-avoid {
            break-inside: avoid;
            page-break-inside: avoid;
          }
        }
      `}</style>

      {/* Header Banner */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm mb-6 no-print">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs uppercase tracking-wider font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200">
                Revision Notes & Exam Cram
              </span>
              {notes && (
                <span className="text-[11px] font-medium text-brand-700 bg-brand-50 px-2.5 py-1 rounded-md border border-brand-200 flex items-center space-x-1">
                  <CheckCircle className="w-3 h-3" />
                  <span>8 High-Yield Sections</span>
                </span>
              )}
            </div>
            <h2 className="text-xl font-bold text-slate-800 mt-2">
              {notes?.title || `Revision Notes: ${document.original_filename}`}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Document: {document.original_filename} • {document.total_pages} Pages • High-Yield Study Booklet
            </p>
          </div>

          <div className="flex items-center space-x-2">
            {notes && (
              <button
                onClick={handlePrint}
                className="flex items-center space-x-2 px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold shadow-sm transition-all border border-slate-200"
                title="Export or print revision notes as PDF"
              >
                <Printer className="w-4 h-4 text-slate-600" />
                <span>Export as PDF</span>
              </button>
            )}

            <button
              onClick={() => handleGenerateNotes(!!notes)}
              disabled={isLoading || document.status !== 'ready'}
              title={document.status !== 'ready' ? 'Document is being processed' : undefined}
              className="flex items-center justify-center space-x-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Compiling...</span>
                </>
              ) : notes ? (
                <>
                  <RefreshCw className="w-4 h-4" />
                  <span>Regenerate Notes</span>
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  <span>Generate Revision Notes</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Printable Header - Visible only in print */}
      <div className="hidden print:block mb-8 border-b pb-4">
        <h1 className="text-2xl font-bold text-slate-900">{notes?.title || document.original_filename}</h1>
        <p className="text-sm text-slate-600 mt-1">
          PaperPilot High-Yield Revision Booklet • {document.original_filename} ({document.total_pages} Pages)
        </p>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center shadow-sm no-print">
          <Loader2 className="w-8 h-8 text-emerald-600 animate-spin mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-slate-700">Synthesizing Revision Notes...</h3>
          <p className="text-xs text-slate-400 mt-1">
            Analyzing definitions, formulas, reactions, comparisons, and exam questions across all pages.
          </p>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-xs text-red-700 mb-6 flex items-center justify-between no-print">
          <span>{error}</span>
          <button
            onClick={() => handleGenerateNotes(false)}
            className="font-semibold underline ml-2 hover:text-red-800"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !notes && !error && (
        <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-12 text-center no-print">
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto mb-4">
            <Zap className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-slate-800">No Revision Notes Generated Yet</h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto mt-2 leading-relaxed">
            Generate an all-in-one high-yield revision sheet covering Chapter Overview, Definitions,
            Key Concepts, Reactions, Formulas, Comparison Tables, FAQs, and Last-Minute Points.
          </p>
          <button
            onClick={() => handleGenerateNotes(false)}
            disabled={document.status !== 'ready'}
            className="mt-5 inline-flex items-center space-x-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400 text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
          >
            <Zap className="w-4 h-4" />
            <span>Generate Revision Notes</span>
          </button>
        </div>
      )}

      {/* Notes Content */}
      {!isLoading && notes && (
        <div className="space-y-6">
          {/* Quick Jump Navigation Bar (no-print) */}
          <div className="sticky top-0 z-10 bg-slate-50/90 backdrop-blur py-2 no-print">
            <div className="flex items-center space-x-1 overflow-x-auto pb-1 scrollbar-thin">
              {[
                { id: 'overview', label: 'Overview', icon: BookOpen },
                { id: 'definitions', label: `Definitions (${notes.definitions.length})`, icon: Bookmark },
                { id: 'concepts', label: `Concepts (${notes.key_concepts.length})`, icon: Lightbulb },
                { id: 'reactions', label: `Reactions (${notes.reactions_equations.length})`, icon: FlaskConical },
                { id: 'formulas', label: `Formulas (${notes.formulas.length})`, icon: Sigma },
                { id: 'differences', label: `Comparisons (${notes.differences_comparisons.length})`, icon: Split },
                { id: 'faqs', label: `FAQs (${notes.faqs.length})`, icon: HelpCircle },
                { id: 'lastminute', label: `Last-Minute (${notes.last_minute_points.length})`, icon: Zap },
              ].map((sec) => (
                <button
                  key={sec.id}
                  onClick={() => scrollToSection(sec.id)}
                  className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all border ${
                    activeSection === sec.id
                      ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm'
                      : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100 hover:text-slate-800'
                  }`}
                >
                  <sec.icon className="w-3.5 h-3.5" />
                  <span>{sec.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Section 1: Chapter Overview */}
          <section id="overview" className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm break-inside-avoid">
            <div className="flex items-center space-x-2 text-slate-800 mb-3 border-b border-slate-100 pb-3">
              <BookOpen className="w-5 h-5 text-emerald-600" />
              <h3 className="font-bold text-sm tracking-wide uppercase">1. Chapter Overview</h3>
            </div>
            <p className="text-xs text-slate-700 leading-relaxed text-justify">
              {notes.chapter_overview}
            </p>
          </section>

          {/* Section 2: Important Definitions */}
          {notes.definitions && notes.definitions.length > 0 && (
            <section id="definitions" className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm break-inside-avoid">
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2 text-slate-800">
                  <Bookmark className="w-5 h-5 text-indigo-600" />
                  <h3 className="font-bold text-sm tracking-wide uppercase">2. Important Definitions</h3>
                </div>
                <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                  {notes.definitions.length} Terms
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {notes.definitions.map((def, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-white hover:border-indigo-300 transition-all flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-indigo-950">{def.term}</span>
                        {def.source_page && (
                          <span className="text-[10px] font-medium text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                            Page {def.source_page}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">
                        {def.definition}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Section 3: Key Concepts */}
          {notes.key_concepts && notes.key_concepts.length > 0 && (
            <section id="concepts" className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm break-inside-avoid">
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2 text-slate-800">
                  <Lightbulb className="w-5 h-5 text-amber-500" />
                  <h3 className="font-bold text-sm tracking-wide uppercase">3. Key Concepts</h3>
                </div>
                <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                  {notes.key_concepts.length} Concepts
                </span>
              </div>
              <div className="space-y-4">
                {notes.key_concepts.map((concept, idx) => (
                  <div key={idx} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50">
                    <div className="flex items-center justify-between mb-1.5">
                      <h4 className="text-xs font-bold text-slate-800">{concept.concept}</h4>
                      {concept.source_page && (
                        <span className="text-[10px] font-medium text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                          Page {concept.source_page}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600 mb-2 leading-relaxed">
                      {concept.summary}
                    </p>
                    {concept.key_points && concept.key_points.length > 0 && (
                      <ul className="space-y-1 pl-4 list-disc text-xs text-slate-600">
                        {concept.key_points.map((pt, pIdx) => (
                          <li key={pIdx} className="leading-relaxed">
                            {pt}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Section 4: Important Reactions & Chemical Equations */}
          {notes.reactions_equations && notes.reactions_equations.length > 0 && (
            <section id="reactions" className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm break-inside-avoid">
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2 text-slate-800">
                  <FlaskConical className="w-5 h-5 text-emerald-600" />
                  <h3 className="font-bold text-sm tracking-wide uppercase">
                    4. Important Reactions & Equations
                  </h3>
                </div>
                <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                  {notes.reactions_equations.length} Equations
                </span>
              </div>
              <div className="space-y-3">
                {notes.reactions_equations.map((rxn, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-xl border border-emerald-100 bg-emerald-50/30 hover:border-emerald-300 transition-all"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-emerald-800 bg-emerald-100/60 px-2.5 py-0.5 rounded-md border border-emerald-200">
                        {rxn.reaction_type}
                      </span>
                      {rxn.source_page && (
                        <span className="text-[10px] font-medium text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                          Page {rxn.source_page}
                        </span>
                      )}
                    </div>

                    <div className="bg-white p-3 rounded-lg border border-slate-200 my-2 text-center text-xs overflow-x-auto">
                      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {rxn.equation_latex}
                      </ReactMarkdown>
                    </div>

                    {rxn.description && (
                      <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                        <strong className="text-slate-700">Observation/Note: </strong>
                        {rxn.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Section 5: Formulas & Quantitative Relationships */}
          {notes.formulas && notes.formulas.length > 0 && (
            <section id="formulas" className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm break-inside-avoid">
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2 text-slate-800">
                  <Sigma className="w-5 h-5 text-blue-600" />
                  <h3 className="font-bold text-sm tracking-wide uppercase">
                    5. Formulas & Quantitative Laws
                  </h3>
                </div>
                <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                  {notes.formulas.length} Formulas
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {notes.formulas.map((form, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-xl border border-blue-100 bg-blue-50/20 hover:border-blue-300 transition-all flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <h4 className="text-xs font-bold text-blue-950">{form.formula_name}</h4>
                        {form.source_page && (
                          <span className="text-[10px] font-medium text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                            Page {form.source_page}
                          </span>
                        )}
                      </div>

                      <div className="bg-white p-2.5 rounded-lg border border-slate-200 my-2 text-center text-xs overflow-x-auto">
                        <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                          {form.formula_latex}
                        </ReactMarkdown>
                      </div>

                      <p className="text-xs text-slate-600 leading-relaxed">
                        <strong className="text-slate-700">Application: </strong>
                        {form.usage}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Section 6: Important Differences & Comparisons */}
          {notes.differences_comparisons && notes.differences_comparisons.length > 0 && (
            <section id="differences" className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm break-inside-avoid">
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2 text-slate-800">
                  <Split className="w-5 h-5 text-violet-600" />
                  <h3 className="font-bold text-sm tracking-wide uppercase">
                    6. Key Differences & Comparisons
                  </h3>
                </div>
                <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                  {notes.differences_comparisons.length} Tables
                </span>
              </div>
              <div className="space-y-6">
                {notes.differences_comparisons.map((diff, idx) => (
                  <div key={idx} className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                    <div className="bg-slate-50 px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
                      <h4 className="text-xs font-bold text-slate-800">{diff.topic}</h4>
                      {diff.source_page && (
                        <span className="text-[10px] font-medium text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                          Page {diff.source_page}
                        </span>
                      )}
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="bg-slate-100/70 border-b border-slate-200 text-slate-700">
                            <th className="p-2.5 font-bold w-1/4">Parameter</th>
                            <th className="p-2.5 font-bold w-3/8 text-violet-900 bg-violet-50/50">
                              {diff.aspect_a}
                            </th>
                            <th className="p-2.5 font-bold w-3/8 text-indigo-900 bg-indigo-50/50">
                              {diff.aspect_b}
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 text-slate-600">
                          {diff.comparison_points.map((pt, pIdx) => (
                            <tr key={pIdx} className="hover:bg-slate-50/60">
                              <td className="p-2.5 font-semibold text-slate-700 bg-slate-50/30">
                                {pt.parameter}
                              </td>
                              <td className="p-2.5 bg-violet-50/20">{pt.item_a}</td>
                              <td className="p-2.5 bg-indigo-50/20">{pt.item_b}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Section 7: Frequently Asked Questions */}
          {notes.faqs && notes.faqs.length > 0 && (
            <section id="faqs" className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm break-inside-avoid">
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2 text-slate-800">
                  <HelpCircle className="w-5 h-5 text-amber-600" />
                  <h3 className="font-bold text-sm tracking-wide uppercase">
                    7. Frequently Asked Questions
                  </h3>
                </div>
                <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                  {notes.faqs.length} Questions
                </span>
              </div>
              <div className="space-y-3">
                {notes.faqs.map((faq, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white transition-all"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start space-x-2">
                        <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded mt-0.5">
                          Q{idx + 1}
                        </span>
                        <h4 className="text-xs font-bold text-slate-800">{faq.question}</h4>
                      </div>
                      {faq.source_page && (
                        <span className="text-[10px] font-medium text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200 whitespace-nowrap">
                          Page {faq.source_page}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600 mt-2 pl-6 leading-relaxed">
                      {faq.answer}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Section 8: Last-Minute Revision Points */}
          {notes.last_minute_points && notes.last_minute_points.length > 0 && (
            <section id="lastminute" className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm break-inside-avoid">
              <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2 text-slate-800">
                  <Zap className="w-5 h-5 text-rose-500" />
                  <h3 className="font-bold text-sm tracking-wide uppercase">
                    8. Last-Minute High-Yield Points
                  </h3>
                </div>
                <span className="text-[11px] font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-md border border-rose-200">
                  Exam Cram
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {notes.last_minute_points.map((pt, idx) => (
                  <div
                    key={idx}
                    className="flex items-start justify-between p-3 rounded-xl border border-rose-100 bg-rose-50/20 text-xs"
                  >
                    <div className="flex items-start space-x-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mt-1.5 flex-shrink-0" />
                      <span className="text-slate-700 leading-relaxed">{pt.point}</span>
                    </div>
                    {pt.source_page && (
                      <span className="text-[10px] font-medium text-slate-500 bg-white px-1.5 py-0.5 rounded border border-slate-200 ml-2 whitespace-nowrap">
                        p.{pt.source_page}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
};

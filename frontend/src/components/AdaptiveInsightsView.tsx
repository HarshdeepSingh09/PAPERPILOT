import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  Loader2,
  RefreshCw,
  CheckCircle,
  Printer,
  FlaskConical,
  Briefcase,
  Users,
  Scale,
  BarChart3,
  Wrench,
  FileText,
  AlertTriangle,
  Calendar,
  CheckSquare,
  ShieldAlert,
  GraduationCap,
} from 'lucide-react';
import {
  DocumentItem,
  DocumentCategory,
  AdaptiveInsightsResponse,
} from '../types';
import { insightsApi } from '../api/client';

interface AdaptiveInsightsViewProps {
  document: DocumentItem;
  onSwitchToChat?: () => void;
}

const CATEGORY_META: Record<
  string,
  { title: string; subtitle: string; badgeClass: string; Icon: React.FC<any> }
> = {
  'Research Paper': {
    title: 'Research Paper Analysis',
    subtitle: 'Objective, methodology, empirical findings, limitations, and contributions',
    badgeClass: 'text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950/60 border-indigo-200 dark:border-indigo-800/60',
    Icon: FlaskConical,
  },
  'Business Report': {
    title: 'Business Report Intelligence',
    subtitle: 'Executive summary, key insights, figures, findings, actions, and recommendations',
    badgeClass: 'text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/60 border-blue-200 dark:border-blue-800/60',
    Icon: Briefcase,
  },
  'Meeting Notes': {
    title: 'Meeting Notes & Action Brief',
    subtitle: 'Summary, decisions, action items, explicit assignees, deadlines, and open issues',
    badgeClass: 'text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-800/60',
    Icon: Users,
  },
  'Legal Document': {
    title: 'Legal Document Overview',
    subtitle: 'Informational extraction of clauses, obligations, dates, parties, and conditions',
    badgeClass: 'text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/60 border-amber-200 dark:border-amber-800/60',
    Icon: Scale,
  },
  'Financial Report': {
    title: 'Financial Report Analysis',
    subtitle: 'Summary, reported figures, revenue/expense lines, trends, and verified ratios',
    badgeClass: 'text-cyan-800 dark:text-cyan-300 bg-cyan-50 dark:bg-cyan-950/60 border-cyan-200 dark:border-cyan-800/60',
    Icon: BarChart3,
  },
  'User Manual / Technical Documentation': {
    title: 'Technical Documentation Guide',
    subtitle: 'Summary, instructions, setup steps, troubleshooting, and operational warnings',
    badgeClass: 'text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-950/60 border-violet-200 dark:border-violet-800/60',
    Icon: Wrench,
  },
  'General Document': {
    title: 'Document Insights',
    subtitle: 'Structured AI summary, key points, and important extracted details',
    badgeClass: 'text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 border-slate-300 dark:border-slate-700',
    Icon: FileText,
  },
};

export const AdaptiveInsightsView: React.FC<AdaptiveInsightsViewProps> = ({
  document,
  onSwitchToChat,
}) => {
  const category = (document.document_category || 'General Document') as DocumentCategory;
  const meta = CATEGORY_META[category] || CATEGORY_META['General Document'];
  const HeaderIcon = meta.Icon;

  const [data, setData] = useState<AdaptiveInsightsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load cached insights automatically when document or category changes
  useEffect(() => {
    let isMounted = true;
    const fetchCached = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const res = await insightsApi.getInsights(document.id, category);
        if (isMounted) setData(res);
      } catch {
        if (isMounted) setData(null);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };
    fetchCached();
    return () => {
      isMounted = false;
    };
  }, [document.id, category]);

  const handleGenerate = async (force = false) => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await insightsApi.generateInsights(document.id, category, force);
      setData(res);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to generate adaptive insights.');
    } finally {
      setIsLoading(false);
    }
  };

  const d = data?.insights || {};
  const fmt = (document.file_format || 'pdf').toUpperCase();
  const unitLabel = document.citation_unit === 'section' ? 'Sections' : 'Pages';

  const renderCitationPill = (cit?: string) =>
    cit ? (
      <span className="text-[10px] font-semibold text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-900 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700 whitespace-nowrap flex-shrink-0">
        {cit}
      </span>
    ) : null;

  return (
    <div className="relative flex-1 min-h-0 overflow-y-auto p-6 md:p-8 max-w-5xl mx-auto w-full print:overflow-visible print:p-0 print:max-w-none print:text-black">
      {/* Header Card */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm mb-6 no-print">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center flex-wrap gap-2">
              <span className={`text-xs uppercase tracking-wider font-semibold px-2.5 py-1 rounded-md border flex items-center space-x-1.5 ${meta.badgeClass}`}>
                <HeaderIcon className="w-3.5 h-3.5" />
                <span>{category}</span>
              </span>
              {data && (
                <span className="text-[11px] font-medium text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-1 rounded-md border border-emerald-200 dark:border-emerald-800/60 flex items-center space-x-1">
                  <CheckCircle className="w-3 h-3" />
                  <span>
                    {data.generation_source === 'gemini' ? 'AI Synthesized & Cached' : 'Extractive Grounded & Cached'}
                  </span>
                </span>
              )}
            </div>
            <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100 mt-2">{meta.title}</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              {document.original_filename} ({fmt}) • {document.total_pages} {unitLabel} • {meta.subtitle}
            </p>
          </div>

          <div className="flex items-center space-x-2 flex-shrink-0">
            {onSwitchToChat && (
              <button
                onClick={onSwitchToChat}
                className="px-3.5 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-semibold border border-slate-200 dark:border-slate-700 transition-all"
              >
                Ask Questions
              </button>
            )}
            {data && (
              <button
                onClick={() => window.print()}
                className="flex items-center space-x-1.5 px-3.5 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-semibold border border-slate-200 dark:border-slate-700 transition-all"
              >
                <Printer className="w-4 h-4 text-slate-600 dark:text-slate-300" />
                <span>Print</span>
              </button>
            )}
            <button
              onClick={() => handleGenerate(!!data)}
              disabled={isLoading || document.status !== 'ready'}
              className="flex items-center space-x-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 dark:disabled:text-slate-600 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Analyzing...</span>
                </>
              ) : data ? (
                <>
                  <RefreshCw className="w-4 h-4" />
                  <span>Regenerate</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Generate Analysis</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/60 rounded-xl text-xs text-red-700 dark:text-red-300 mb-6 flex items-center justify-between no-print">
          <span>{error}</span>
          <button onClick={() => handleGenerate(false)} className="font-semibold underline ml-2">
            Retry
          </button>
        </div>
      )}

      {isLoading && !data && (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-12 text-center shadow-sm">
          <Loader2 className="w-8 h-8 text-brand-600 dark:text-brand-400 animate-spin mx-auto mb-3" />
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">Running {meta.title}...</h3>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
            Extracting category-specific insights strictly grounded in the document text.
          </p>
        </div>
      )}

      {!isLoading && !data && !error && (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 p-12 text-center">
          <div className="w-12 h-12 rounded-2xl bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 flex items-center justify-center mx-auto mb-4">
            <HeaderIcon className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-slate-800 dark:text-slate-100">No {meta.title} Generated Yet</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto mt-2 leading-relaxed">
            {meta.subtitle}. Click below to extract structured insights directly from {document.original_filename}.
          </p>
          <button
            onClick={() => handleGenerate(false)}
            disabled={document.status !== 'ready'}
            className="mt-5 inline-flex items-center space-x-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 dark:disabled:text-slate-600 text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
          >
            <Sparkles className="w-4 h-4" />
            <span>Generate {meta.title}</span>
          </button>
        </div>
      )}

      {!isLoading && data && (
        <div className="space-y-6">
          {/* === CATEGORY: RESEARCH PAPER === */}
          {category === 'Research Paper' && (
            <>
              <SectionCard title="Research Summary" text={d.research_summary} />
              <SectionCard title="Research Objective" text={d.research_objective} />
              <BulletCard title="Methodology Analysis" items={d.methodology_analysis} />
              <CitedListCard
                title="Key Findings"
                items={(d.key_findings || []).map((x: any) => ({
                  text: typeof x === 'string' ? x : x.finding,
                  citation: x?.citation,
                }))}
                renderCitationPill={renderCitationPill}
              />
              <BulletCard title="Limitations" items={d.limitations} emptyText="No explicit limitations stated in the extracted text." />
              <BulletCard title="Important Contributions" items={d.important_contributions} />
            </>
          )}

          {/* === CATEGORY: BUSINESS REPORT === */}
          {category === 'Business Report' && (
            <>
              <SectionCard title="Executive Summary" text={d.executive_summary} />
              <CitedListCard
                title="Key Insights"
                items={(d.key_insights || []).map((x: any) => ({
                  text: typeof x === 'string' ? x : x.insight,
                  citation: x?.citation,
                }))}
                renderCitationPill={renderCitationPill}
              />
              <FiguresTableCard
                title="Important Figures (Reported Only)"
                rows={(d.important_figures || []).map((f: any) => ({
                  col1: f.metric,
                  col2: f.value,
                  col3: f.context,
                  citation: f.citation,
                }))}
                headers={['Metric', 'Value', 'Context', 'Source']}
                emptyText="No explicit quantitative business figures identified in extracted text."
              />
              <BulletCard title="Business Findings" items={d.business_findings} />
              <BulletCard title="Action Items" items={d.action_items} emptyText="No explicit action items stated." />
              <BulletCard title="Recommendations" items={d.recommendations} emptyText="No explicit recommendations stated." />
            </>
          )}

          {/* === CATEGORY: MEETING NOTES === */}
          {category === 'Meeting Notes' && (
            <>
              <SectionCard title="Meeting Summary" text={d.meeting_summary} />
              <CitedListCard
                title="Important Decisions"
                items={(d.important_decisions || []).map((x: any) => ({
                  text: typeof x === 'string' ? x : x.decision,
                  citation: x?.citation,
                }))}
                emptyText="No explicit decisions recorded in these meeting notes."
                renderCitationPill={renderCitationPill}
              />
              <CitedListCard
                title="Action Items"
                icon={<CheckSquare className="w-4 h-4 text-emerald-600" />}
                items={(d.action_items || []).map((x: any) => ({
                  text: typeof x === 'string' ? x : x.action,
                  citation: x?.citation,
                }))}
                emptyText="No explicit action items identified."
                renderCitationPill={renderCitationPill}
              />
              <FiguresTableCard
                title="Assigned Responsibilities (Explicitly Stated)"
                rows={(d.assigned_responsibilities || []).map((r: any) => ({
                  col1: r.assignee,
                  col2: r.task,
                  col3: '',
                  citation: r.citation,
                }))}
                headers={['Assignee', 'Responsibility', '', 'Source']}
                threeCol
                emptyText="No explicit individual assignees found in the document."
              />
              <FiguresTableCard
                title="Deadlines Mentioned"
                icon={<Calendar className="w-4 h-4 text-brand-600" />}
                rows={(d.deadlines_mentioned || []).map((dl: any) => ({
                  col1: dl.deadline,
                  col2: dl.item,
                  col3: '',
                  citation: dl.citation,
                }))}
                headers={['Deadline', 'Deliverable / Item', '', 'Source']}
                threeCol
                emptyText="No explicit deadlines mentioned in the document."
              />
              <BulletCard title="Unresolved Issues" items={d.unresolved_issues} emptyText="No unresolved issues explicitly noted." />
            </>
          )}

          {/* === CATEGORY: LEGAL DOCUMENT === */}
          {category === 'Legal Document' && (
            <>
              <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 rounded-2xl p-4 flex items-start space-x-3 text-xs text-amber-900 dark:text-amber-200">
                <ShieldAlert className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold block mb-0.5">Informational Only — Not Legal Advice</span>
                  <span>
                    {d.disclaimer ||
                      'This summary organizes text from the uploaded document for informational purposes only and is not legal advice.'}
                  </span>
                </div>
              </div>
              <SectionCard title="Document Overview" text={d.document_overview} />
              <div className="bg-white dark:bg-slate-900 print:bg-white rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 mb-3">Parties Involved</h3>
                {d.parties_involved && d.parties_involved.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {d.parties_involved.map((p: string, idx: number) => (
                      <span
                        key={idx}
                        className="text-xs font-semibold text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-lg border border-slate-200 dark:border-slate-700"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 dark:text-slate-500">
                    No named parties automatically isolated; ask in Chat for specific clauses.
                  </p>
                )}
              </div>
              <div className="bg-white dark:bg-slate-900 print:bg-white rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 mb-3">Important Clauses</h3>
                <div className="space-y-3">
                  {(d.important_clauses || []).map((cl: any, idx: number) => (
                    <div
                      key={idx}
                      className="p-3.5 bg-slate-50 dark:bg-slate-800/70 rounded-xl border border-slate-200 dark:border-slate-700/80"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-bold text-slate-800 dark:text-slate-100">
                          {cl.clause_title || `Clause ${idx + 1}`}
                        </span>
                        {renderCitationPill(cl.citation)}
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">{cl.summary}</p>
                    </div>
                  ))}
                </div>
              </div>
              <FiguresTableCard
                title="Explicit Obligations"
                rows={(d.obligations || []).map((o: any) => ({
                  col1: o.party,
                  col2: o.obligation,
                  col3: '',
                  citation: o.citation,
                }))}
                headers={['Party', 'Obligation', '', 'Source']}
                threeCol
                emptyText="No explicit obligations extracted."
              />
              <FiguresTableCard
                title="Dates and Deadlines"
                rows={(d.dates_and_deadlines || []).map((dt: any) => ({
                  col1: dt.date_or_period,
                  col2: dt.context,
                  col3: '',
                  citation: dt.citation,
                }))}
                headers={['Date / Period', 'Context', '', 'Source']}
                threeCol
                emptyText="No specific dates or deadlines isolated."
              />
              <BulletCard title="Potentially Important Conditions" items={d.important_conditions} emptyText="No conditional clauses highlighted." />
            </>
          )}

          {/* === CATEGORY: FINANCIAL REPORT === */}
          {category === 'Financial Report' && (
            <>
              <SectionCard title="Financial Summary" text={d.financial_summary} />
              <FiguresTableCard
                title="Important Figures (Reported)"
                rows={(d.important_figures || []).map((f: any) => ({
                  col1: f.metric,
                  col2: f.value,
                  col3: f.period,
                  citation: f.citation,
                }))}
                headers={['Metric', 'Value', 'Period', 'Source']}
                emptyText="No explicit financial figures extracted."
              />
              <FiguresTableCard
                title="Revenue & Expense Information"
                rows={(d.revenue_and_expenses || []).map((r: any) => ({
                  col1: r.item,
                  col2: r.amount,
                  col3: r.details,
                  citation: r.citation,
                }))}
                headers={['Line Item', 'Amount', 'Details', 'Source']}
                emptyText="No revenue or expense items isolated."
              />
              <BulletCard title="Key Financial Trends" items={d.key_financial_trends} emptyText="No explicit financial trends reported." />
              <FiguresTableCard
                title="Important Ratios (Reported / Directly Supported Only)"
                rows={(d.important_ratios || []).map((rt: any) => ({
                  col1: rt.ratio_name,
                  col2: rt.value,
                  col3: rt.note,
                  citation: rt.citation,
                }))}
                headers={['Ratio', 'Value', 'Note', 'Source']}
                emptyText="Insufficient explicitly reported financial data to state verified ratios (unsupported metrics are never fabricated)."
              />
            </>
          )}

          {/* === CATEGORY: USER MANUAL / TECHNICAL DOCUMENTATION === */}
          {category === 'User Manual / Technical Documentation' && (
            <>
              <SectionCard title="Documentation Summary" text={d.documentation_summary} />
              {d.important_warnings && d.important_warnings.length > 0 && (
                <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 rounded-2xl p-6 shadow-sm">
                  <h3 className="text-sm font-bold text-amber-900 dark:text-amber-200 flex items-center space-x-2 mb-3">
                    <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                    <span>Important Warnings & Cautions</span>
                  </h3>
                  <div className="space-y-2">
                    {d.important_warnings.map((w: any, idx: number) => (
                      <div
                        key={idx}
                        className="flex items-start justify-between gap-2 p-3 bg-white/80 dark:bg-slate-900/70 rounded-xl border border-amber-200 dark:border-amber-800/60 text-xs text-amber-950 dark:text-amber-100"
                      >
                        <span>{typeof w === 'string' ? w : w.warning}</span>
                        {renderCitationPill(w?.citation)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="bg-white dark:bg-slate-900 print:bg-white rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 mb-3">Setup Steps</h3>
                {d.setup_steps && d.setup_steps.length > 0 ? (
                  <div className="space-y-2.5">
                    {d.setup_steps.map((st: any, idx: number) => (
                      <div
                        key={idx}
                        className="flex items-start justify-between gap-3 p-3.5 bg-slate-50 dark:bg-slate-800/70 rounded-xl border border-slate-200 dark:border-slate-700/80 text-xs"
                      >
                        <div className="flex items-start space-x-3">
                          <span className="w-6 h-6 rounded-lg bg-violet-100 dark:bg-violet-950/70 text-violet-800 dark:text-violet-300 font-bold flex items-center justify-center flex-shrink-0">
                            {st.step_number || idx + 1}
                          </span>
                          <div>
                            <div className="font-bold text-slate-800 dark:text-slate-100">{st.title}</div>
                            <p className="text-slate-600 dark:text-slate-300 mt-0.5 leading-relaxed">{st.detail}</p>
                          </div>
                        </div>
                        {renderCitationPill(st.citation)}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 dark:text-slate-500">
                    No numbered setup sequence identified in this document.
                  </p>
                )}
              </div>
              <CitedListCard
                title="Important Instructions"
                items={(d.important_instructions || []).map((x: any) => ({
                  text: typeof x === 'string' ? x : x.instruction,
                  citation: x?.citation,
                }))}
                renderCitationPill={renderCitationPill}
              />
              <FiguresTableCard
                title="Troubleshooting Information"
                rows={(d.troubleshooting || []).map((t: any) => ({
                  col1: t.issue,
                  col2: t.resolution,
                  col3: '',
                  citation: t.citation,
                }))}
                headers={['Issue / Error', 'Resolution / Guidance', '', 'Source']}
                threeCol
                emptyText="No troubleshooting section identified in this document."
              />
            </>
          )}

          {/* === CATEGORY: GENERAL DOCUMENT === */}
          {category === 'General Document' && (
            <>
              <SectionCard title="AI Summary" text={d.ai_summary} />
              <CitedListCard
                title="Key Points"
                items={(d.key_points || []).map((x: any) => ({
                  text: typeof x === 'string' ? x : x.point,
                  citation: x?.citation,
                }))}
                renderCitationPill={renderCitationPill}
              />
              <div className="bg-white dark:bg-slate-900 print:bg-white rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 mb-3">Important Information</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {(d.important_information || []).map((info: any, idx: number) => (
                    <div
                      key={idx}
                      className="p-3.5 bg-slate-50 dark:bg-slate-800/70 rounded-xl border border-slate-200 dark:border-slate-700/80"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-bold text-slate-800 dark:text-slate-100">
                          {info.topic || 'Detail'}
                        </span>
                        {renderCitationPill(info.citation)}
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">{info.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

/* --- Reusable Clean Display Cards --- */

const SectionCard: React.FC<{ title: string; text?: string }> = ({ title, text }) => (
  <div className="bg-white dark:bg-slate-900 print:bg-white rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
    <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 print:text-slate-900 mb-2.5">{title}</h3>
    <p className="text-xs text-slate-700 dark:text-slate-300 print:text-slate-800 leading-relaxed bg-slate-50 dark:bg-slate-800/70 print:bg-slate-50 p-4 rounded-xl border border-slate-100 dark:border-slate-700/70">
      {text || 'No summary text extracted.'}
    </p>
  </div>
);

const BulletCard: React.FC<{ title: string; items?: string[]; emptyText?: string }> = ({
  title,
  items,
  emptyText = 'None explicitly identified in document.',
}) => (
  <div className="bg-white dark:bg-slate-900 print:bg-white rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
    <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 print:text-slate-900 mb-3">{title}</h3>
    {items && items.length > 0 ? (
      <ul className="space-y-2 text-xs text-slate-700 dark:text-slate-200 print:text-slate-800">
        {items.map((item, idx) => (
          <li
            key={idx}
            className="flex items-start space-x-2.5 p-3 bg-slate-50 dark:bg-slate-800/70 print:bg-slate-50 rounded-xl border border-slate-100 dark:border-slate-700/70"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-brand-600 dark:bg-brand-400 mt-1.5 flex-shrink-0" />
            <span className="leading-relaxed">{item}</span>
          </li>
        ))}
      </ul>
    ) : (
      <p className="text-xs text-slate-400 dark:text-slate-500 italic">{emptyText}</p>
    )}
  </div>
);

const CitedListCard: React.FC<{
  title: string;
  items: Array<{ text: string; citation?: string }>;
  icon?: React.ReactNode;
  emptyText?: string;
  renderCitationPill: (c?: string) => React.ReactNode;
}> = ({ title, items, icon, emptyText = 'None identified in document.', renderCitationPill }) => (
  <div className="bg-white dark:bg-slate-900 print:bg-white rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
    <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 print:text-slate-900 mb-3 flex items-center space-x-2">
      {icon}
      <span>{title}</span>
    </h3>
    {items.length > 0 ? (
      <div className="space-y-2.5">
        {items.map((item, idx) => (
          <div
            key={idx}
            className="flex items-start justify-between gap-3 p-3.5 bg-slate-50 dark:bg-slate-800/70 print:bg-slate-50 rounded-xl border border-slate-100 dark:border-slate-700/70 text-xs text-slate-700 dark:text-slate-200 print:text-slate-800"
          >
            <span className="leading-relaxed">{item.text}</span>
            {renderCitationPill(item.citation)}
          </div>
        ))}
      </div>
    ) : (
      <p className="text-xs text-slate-400 dark:text-slate-500 italic">{emptyText}</p>
    )}
  </div>
);

const FiguresTableCard: React.FC<{
  title: string;
  rows: Array<{ col1: string; col2: string; col3?: string; citation?: string }>;
  headers: [string, string, string, string];
  threeCol?: boolean;
  icon?: React.ReactNode;
  emptyText: string;
}> = ({ title, rows, headers, threeCol = false, icon, emptyText }) => (
  <div className="bg-white dark:bg-slate-900 print:bg-white rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
    <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 print:text-slate-900 mb-3 flex items-center space-x-2">
      {icon}
      <span>{title}</span>
    </h3>
    {rows.length > 0 ? (
      <div className="overflow-x-auto border border-slate-200 dark:border-slate-700 rounded-xl">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200">
              <th className="p-2.5 font-bold">{headers[0]}</th>
              <th className="p-2.5 font-bold">{headers[1]}</th>
              {!threeCol && <th className="p-2.5 font-bold">{headers[2]}</th>}
              <th className="p-2.5 font-bold text-right">{headers[3]}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-700 text-slate-600 dark:text-slate-300">
            {rows.map((r, idx) => (
              <tr key={idx} className="hover:bg-slate-50/70 dark:hover:bg-slate-800/50">
                <td className="p-2.5 font-semibold text-slate-800 dark:text-slate-100">{r.col1}</td>
                <td className="p-2.5">{r.col2}</td>
                {!threeCol && <td className="p-2.5">{r.col3}</td>}
                <td className="p-2.5 text-right whitespace-nowrap font-medium text-slate-500 dark:text-slate-400">
                  {r.citation || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <p className="text-xs text-slate-400 dark:text-slate-500 italic">{emptyText}</p>
    )}
  </div>
);

export const ExamIntelligencePlaceholder: React.FC<{ document: DocumentItem }> = ({ document }) => (
  <div className="relative flex-1 min-h-0 overflow-y-auto p-6 md:p-8 max-w-4xl mx-auto w-full">
    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-brand-300 dark:border-brand-700 p-10 text-center shadow-sm">
      <div className="w-14 h-14 rounded-2xl bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 flex items-center justify-center mx-auto mb-4">
        <GraduationCap className="w-7 h-7" />
      </div>
      <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-brand-50 dark:bg-brand-950/60 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800">
        Upcoming Feature • Future Phase
      </span>
      <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100 mt-3">Exam Intelligence</h2>
      <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto mt-2 leading-relaxed">
        Planned for a future PaperPilot phase for{' '}
        <span className="font-semibold text-slate-700 dark:text-slate-200">{document.original_filename}</span>. This
        module will analyze question weightage, high-frequency exam concepts, and timed mock paper readiness alongside
        your existing AI Summary, Interactive Quiz, Revision Notes, and Document Chat tools.
      </p>
    </div>
  </div>
);

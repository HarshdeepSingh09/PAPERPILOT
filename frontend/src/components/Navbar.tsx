import React from 'react';
import {
  BookOpen,
  Sparkles,
  Layers,
  Zap,
  GraduationCap,
  FlaskConical,
  Briefcase,
  Users,
  Scale,
  BarChart3,
  Wrench,
  FileText,
  PanelLeft,
  User as UserIcon,
  LogOut,
} from 'lucide-react';
import { DocumentCategory } from '../types';
import { ThemeToggle } from '../context/ThemeContext';
import { useRouter } from '../context/RouterContext';

export type ActiveTab =
  | 'chat'
  | 'summary'
  | 'quiz'
  | 'revision'
  | 'exam_placeholder'
  | 'insights';

interface NavbarProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  hasSelectedDocument: boolean;
  documentCategory?: DocumentCategory;
  onToggleMobileSidebar?: () => void;
  userName?: string;
  userEmail?: string;
  onLogout?: () => void;
}

const INSIGHTS_TAB_CONFIG: Record<string, { label: string; Icon: React.FC<any> }> = {
  'Research Paper': { label: 'Research Analysis', Icon: FlaskConical },
  'Business Report': { label: 'Business Insights', Icon: Briefcase },
  'Meeting Notes': { label: 'Meeting Brief', Icon: Users },
  'Legal Document': { label: 'Legal Review', Icon: Scale },
  'Financial Report': { label: 'Financial Analysis', Icon: BarChart3 },
  'User Manual / Technical Documentation': { label: 'Manual Guide', Icon: Wrench },
  'General Document': { label: 'Document Insights', Icon: FileText },
};

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  hasSelectedDocument,
  documentCategory = 'General Document',
  onToggleMobileSidebar,
  userName,
  userEmail,
  onLogout,
}) => {
  const { navigate } = useRouter();
  const isEducational = documentCategory === 'Educational Material';
  const insightsCfg = INSIGHTS_TAB_CONFIG[documentCategory] || INSIGHTS_TAB_CONFIG['General Document'];
  const InsightsIcon = insightsCfg.Icon;

  return (
    <header className="relative min-h-16 flex-shrink-0 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-2 shadow-sm z-30 transition-colors duration-200 print:hidden">
      <div className="flex items-center space-x-2.5 sm:space-x-3">
        {onToggleMobileSidebar && (
          <button
            type="button"
            onClick={onToggleMobileSidebar}
            aria-label="Toggle document library"
            className="lg:hidden p-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
        )}

        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate('/');
          }}
          title="Back to PaperPilot Home"
          className="flex items-center space-x-2.5 sm:space-x-3 focus:outline-none focus:ring-2 focus:ring-brand-500/40 rounded-xl pr-1"
        >
          <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center text-white shadow-md shadow-brand-500/20 flex-shrink-0">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg sm:text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-brand-700 to-indigo-600 dark:from-brand-400 dark:to-indigo-300">
                PaperPilot
              </h1>
              <span className="hidden sm:inline text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-950 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800">
                Workspace
              </span>
            </div>
            <p className="hidden sm:block text-xs text-slate-500 dark:text-slate-400">
              AI Document Intelligence Platform
            </p>
          </div>
        </a>
      </div>

      {/* Adaptive Navigation Mode Tabs & Theme Toggle */}
      <div className="flex items-center space-x-2 max-w-full overflow-x-auto">
        <nav className="flex items-center space-x-1 bg-slate-100 dark:bg-slate-800/90 p-1 rounded-xl overflow-x-auto max-w-full border border-transparent dark:border-slate-700/60">
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex items-center space-x-1.5 sm:space-x-2 px-3 sm:px-3.5 py-1.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${
              activeTab === 'chat'
                ? 'bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-sm'
                : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>Chat & RAG</span>
          </button>

          {(!hasSelectedDocument || isEducational) ? (
            <>
              <button
                onClick={() => setActiveTab('summary')}
                disabled={!hasSelectedDocument}
                className={`flex items-center space-x-1.5 sm:space-x-2 px-3 sm:px-3.5 py-1.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${
                  activeTab === 'summary'
                    ? 'bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-sm'
                    : hasSelectedDocument
                    ? 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
                    : 'text-slate-400 dark:text-slate-600 cursor-not-allowed'
                }`}
              >
                <BookOpen className="w-4 h-4" />
                <span>Summary</span>
              </button>

              <button
                onClick={() => setActiveTab('quiz')}
                disabled={!hasSelectedDocument}
                className={`flex items-center space-x-1.5 sm:space-x-2 px-3 sm:px-3.5 py-1.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${
                  activeTab === 'quiz'
                    ? 'bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-sm'
                    : hasSelectedDocument
                    ? 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
                    : 'text-slate-400 dark:text-slate-600 cursor-not-allowed'
                }`}
              >
                <Layers className="w-4 h-4" />
                <span>Quiz</span>
              </button>

              <button
                onClick={() => setActiveTab('revision')}
                disabled={!hasSelectedDocument}
                className={`flex items-center space-x-1.5 sm:space-x-2 px-3 sm:px-3.5 py-1.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${
                  activeTab === 'revision'
                    ? 'bg-white dark:bg-slate-900 text-emerald-700 dark:text-emerald-300 shadow-sm'
                    : hasSelectedDocument
                    ? 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
                    : 'text-slate-400 dark:text-slate-600 cursor-not-allowed'
                }`}
              >
                <Zap className="w-4 h-4" />
                <span>Revision Notes</span>
              </button>

              {hasSelectedDocument && (
                <button
                  onClick={() => setActiveTab('exam_placeholder')}
                  className={`flex items-center space-x-1.5 px-3 py-1.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${
                    activeTab === 'exam_placeholder'
                      ? 'bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                  }`}
                >
                  <GraduationCap className="w-4 h-4" />
                  <span>Exam Prep</span>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-brand-100 dark:bg-brand-950 text-brand-700 dark:text-brand-300">
                    Soon
                  </span>
                </button>
              )}
            </>
          ) : (
            <button
              onClick={() => setActiveTab('insights')}
              className={`flex items-center space-x-1.5 sm:space-x-2 px-3 sm:px-3.5 py-1.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${
                activeTab === 'insights'
                  ? 'bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-sm'
                  : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
              }`}
            >
              <InsightsIcon className="w-4 h-4" />
              <span>{insightsCfg.label}</span>
            </button>
          )}
        </nav>

        <div className="flex items-center space-x-2 flex-shrink-0 pl-1">
          {userName && (
            <div
              title={userEmail || userName}
              className="hidden xl:flex items-center space-x-1.5 px-2.5 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 max-w-[160px]"
            >
              <UserIcon className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400 flex-shrink-0" />
              <span className="truncate">{userName}</span>
            </div>
          )}

          <ThemeToggle className="flex-shrink-0" />

          {onLogout && (
            <button
              type="button"
              onClick={onLogout}
              title="Sign out of PaperPilot"
              aria-label="Log out"
              className="inline-flex items-center space-x-1.5 px-2.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/90 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 hover:border-red-200 dark:hover:border-red-900/60 transition-all"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};

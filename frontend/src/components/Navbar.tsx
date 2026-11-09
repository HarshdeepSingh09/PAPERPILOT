import React from 'react';
import { BookOpen, Sparkles, Layers, Zap } from 'lucide-react';

interface NavbarProps {
  activeTab: 'chat' | 'summary' | 'quiz' | 'revision';
  setActiveTab: (tab: 'chat' | 'summary' | 'quiz' | 'revision') => void;
  hasSelectedDocument: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  hasSelectedDocument,
}) => {
  return (
    <header className="h-16 border-b border-slate-200 bg-white px-6 flex items-center justify-between shadow-sm sticky top-0 z-30">
      <div className="flex items-center space-x-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center text-white shadow-md shadow-brand-500/20">
          <BookOpen className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-brand-700 to-indigo-600">
              PaperPilot
            </h1>
            <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-200">
              v0.1
            </span>
          </div>
          <p className="text-xs text-slate-500">AI-Powered Document Intelligence</p>
        </div>
      </div>

      {/* Navigation Mode Tabs */}
      <nav className="flex items-center space-x-1 bg-slate-100 p-1 rounded-xl">
        <button
          onClick={() => setActiveTab('chat')}
          className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'chat'
              ? 'bg-white text-brand-700 shadow-sm'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          <Sparkles className="w-4 h-4" />
          <span>Chat & RAG</span>
        </button>

        <button
          onClick={() => setActiveTab('summary')}
          disabled={!hasSelectedDocument}
          className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'summary'
              ? 'bg-white text-brand-700 shadow-sm'
              : hasSelectedDocument
              ? 'text-slate-600 hover:text-slate-900'
              : 'text-slate-400 cursor-not-allowed'
          }`}
        >
          <BookOpen className="w-4 h-4" />
          <span>Summary</span>
        </button>

        <button
          onClick={() => setActiveTab('quiz')}
          disabled={!hasSelectedDocument}
          className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'quiz'
              ? 'bg-white text-brand-700 shadow-sm'
              : hasSelectedDocument
              ? 'text-slate-600 hover:text-slate-900'
              : 'text-slate-400 cursor-not-allowed'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Quiz</span>
        </button>

        <button
          onClick={() => setActiveTab('revision')}
          disabled={!hasSelectedDocument}
          className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'revision'
              ? 'bg-white text-emerald-700 shadow-sm'
              : hasSelectedDocument
              ? 'text-slate-600 hover:text-slate-900'
              : 'text-slate-400 cursor-not-allowed'
          }`}
        >
          <Zap className="w-4 h-4" />
          <span>Revision Notes</span>
        </button>
      </nav>
    </header>
  );
};

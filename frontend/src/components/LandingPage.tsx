import React, { useState } from 'react';
import {
  BookOpen,
  Sparkles,
  FileText,
  Layers,
  Zap,
  GraduationCap,
  UploadCloud,
  BrainCircuit,
  Compass,
  CheckCircle2,
  ArrowRight,
  Menu,
  X,
  ShieldCheck,
  Search,
  FolderKanban,
} from 'lucide-react';
import { ThemeToggle } from '../context/ThemeContext';
import { useRouter } from '../context/RouterContext';
import { useAuth } from '../context/AuthContext';
import { HeroProductPreview } from './HeroProductPreview';

export const LandingPage: React.FC = () => {
  const { navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleOpenApp = () => {
    setMobileMenuOpen(false);
    navigate('/app');
  };

  const handleSignIn = () => {
    setMobileMenuOpen(false);
    navigate(isAuthenticated ? '/app' : '/login');
  };

  const scrollToSection = (id: string) => {
    setMobileMenuOpen(false);
    const el = window.document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const featureCards = [
    {
      title: 'AI Document Chat',
      description:
        'Ask natural-language questions against PDF, Word, and text documents. Responses stay grounded in extracted excerpts with page or section citations.',
      Icon: Sparkles,
      accent: 'text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-950/70 border-brand-200 dark:border-brand-800/60',
      upcoming: false,
    },
    {
      title: 'Smart Summaries',
      description:
        'Synthesize executive overviews, core takeaways, terminology definitions, KaTeX equations, and verified page references stored cleanly for revisit.',
      Icon: BookOpen,
      accent: 'text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/70 border-indigo-200 dark:border-indigo-800/60',
      upcoming: false,
    },
    {
      title: 'Interactive Quizzes',
      description:
        'Test retention with single-question active recall players, configurable question counts and difficulty, locked answers prior to submit, and explanations.',
      Icon: Layers,
      accent: 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/70 border-emerald-200 dark:border-emerald-800/60',
      upcoming: false,
    },
    {
      title: 'Revision Notes',
      description:
        'Compile structured 8-section study sheets featuring definitions, reactions, formulas, comparison tables, FAQs, and clean print-to-PDF export.',
      Icon: Zap,
      accent: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/70 border-amber-200 dark:border-amber-800/60',
      upcoming: false,
    },
    {
      title: 'Document Intelligence',
      description:
        'Automatically detect and adapt analysis tools across Research Papers, Business & Financial Reports, Meeting Notes, Legal Contracts, and Manuals.',
      Icon: BrainCircuit,
      accent: 'text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-950/70 border-cyan-200 dark:border-cyan-800/60',
      upcoming: false,
    },
    {
      title: 'Exam Intelligence',
      description:
        'Question-paper pattern insights, topic emphasis analysis, and targeted revision planning designed for upcoming academic workflows.',
      Icon: GraduationCap,
      accent: 'text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-950/70 border-violet-200 dark:border-violet-800/60',
      upcoming: true,
    },
  ];

  const workflowSteps = [
    {
      step: '01',
      title: 'Upload',
      description:
        'Upload your PDF, Word (.docx), or text (.txt) document. PaperPilot validates the file and extracts structured content while preserving page or section references.',
      Icon: UploadCloud,
    },
    {
      step: '02',
      title: 'Understand',
      description:
        'PaperPilot extracts and analyses its content, automatically classifies the document category, generates semantic embeddings, and builds an isolated vector index.',
      Icon: BrainCircuit,
    },
    {
      step: '03',
      title: 'Explore',
      description:
        'Chat with source-grounded citations, generate structured summaries, practice interactive quizzes, or inspect category-specific insights in one workspace.',
      Icon: Compass,
    },
  ];

  const whyPillars = [
    {
      title: 'One place for document understanding',
      description:
        'Move seamlessly from textbooks and research papers to meeting notes, reports, manuals, and legal contracts in a unified interface.',
      Icon: FolderKanban,
    },
    {
      title: 'AI-powered information retrieval',
      description:
        'Combines ChromaDB vector similarity search with intent-aware metadata and page or section routing to locate relevant passages fast.',
      Icon: Search,
    },
    {
      title: 'Source-grounded answers',
      description:
        'Every response is constrained strictly to retrieved excerpts with clickable page or section citations—and clearly states when information is missing.',
      Icon: ShieldCheck,
    },
    {
      title: 'Interactive learning',
      description:
        'Turn study material into self-paced quizzes with immediate explanations, KaTeX equations, and printable 8-section revision booklets.',
      Icon: Layers,
    },
    {
      title: 'Organised document management',
      description:
        'Keep every uploaded file, detected category, custom override, cached analysis, and chat thread cleanly organized and isolated per document.',
      Icon: CheckCircle2,
    },
  ];

  return (
    <div className="relative h-full w-full overflow-y-auto overflow-x-hidden scroll-smooth bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors duration-200">
      {/* Subtle Ambient Background Gradient */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-gradient-to-b from-brand-50/90 via-indigo-50/30 to-transparent dark:from-brand-950/35 dark:via-slate-900/20 dark:to-transparent"
      />

      {/* Section 1: Sticky Responsive Navigation */}
      <header className="sticky top-0 z-40 border-b border-slate-200/80 dark:border-slate-800/80 bg-white/85 dark:bg-slate-950/85 backdrop-blur-md transition-colors duration-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Logo & Brand */}
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault();
              window.document.querySelector('[data-landing-top]')?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="flex items-center space-x-2.5 focus:outline-none focus:ring-2 focus:ring-brand-500/40 rounded-xl pr-2"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center text-white shadow-md shadow-brand-500/20">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <span className="text-lg font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-brand-700 to-indigo-600 dark:from-brand-400 dark:to-indigo-300">
                PaperPilot
              </span>
            </div>
          </a>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center space-x-7 text-sm font-medium text-slate-600 dark:text-slate-300">
            <button
              type="button"
              onClick={() => scrollToSection('features')}
              className="hover:text-brand-600 dark:hover:text-brand-400 transition-colors focus:outline-none focus:text-brand-600"
            >
              Features
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('how-it-works')}
              className="hover:text-brand-600 dark:hover:text-brand-400 transition-colors focus:outline-none focus:text-brand-600"
            >
              How It Works
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('about')}
              className="hover:text-brand-600 dark:hover:text-brand-400 transition-colors focus:outline-none focus:text-brand-600"
            >
              About
            </button>
          </nav>

          {/* Right Actions */}
          <div className="hidden md:flex items-center space-x-3">
            <ThemeToggle />
            {!isAuthenticated && (
              <button
                type="button"
                onClick={handleSignIn}
                className="px-3.5 py-2 rounded-xl text-sm font-semibold text-slate-700 dark:text-slate-200 hover:text-brand-600 dark:hover:text-brand-400 hover:bg-slate-100 dark:hover:bg-slate-800/70 transition-colors"
              >
                Sign In
              </button>
            )}
            <button
              type="button"
              onClick={handleOpenApp}
              className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold shadow-sm shadow-brand-600/20 transition-all focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:focus:ring-offset-slate-950"
            >
              <span>{isAuthenticated ? 'Open Workspace' : 'Try PaperPilot'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Mobile Controls */}
          <div className="flex md:hidden items-center space-x-2">
            <ThemeToggle />
            <button
              type="button"
              aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500/40"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Drawer */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-4 space-y-2">
            <button
              type="button"
              onClick={() => scrollToSection('features')}
              className="block w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              Features
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('how-it-works')}
              className="block w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              How It Works
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('about')}
              className="block w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              About
            </button>
            {!isAuthenticated && (
              <button
                type="button"
                onClick={handleSignIn}
                className="block w-full text-left px-3 py-2 rounded-lg text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                Sign In
              </button>
            )}
            <button
              type="button"
              onClick={handleOpenApp}
              className="w-full mt-2 inline-flex items-center justify-center space-x-1.5 px-4 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold shadow-sm"
            >
              <span>{isAuthenticated ? 'Open Workspace' : 'Try PaperPilot'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </header>

      {/* Section 2: Hero */}
      <section data-landing-top className="relative pt-14 pb-20 md:pt-20 md:pb-24 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          <div className="lg:col-span-5 text-center lg:text-left">
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-brand-50 dark:bg-brand-950/80 border border-brand-200 dark:border-brand-800 text-brand-700 dark:text-brand-300 text-xs font-semibold mb-6">
              <Sparkles className="w-3.5 h-3.5" />
              <span>AI Document Intelligence Workspace</span>
            </div>

            <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-slate-900 dark:text-white leading-[1.12]">
              Your Documents. Your Knowledge.{' '}
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-brand-600 to-indigo-500 dark:from-brand-400 dark:to-indigo-300">
                One AI.
              </span>
            </h1>

            <p className="mt-5 text-base sm:text-lg text-slate-600 dark:text-slate-300 leading-relaxed max-w-xl mx-auto lg:mx-0">
              Turn documents into knowledge. Chat with your files, generate intelligent summaries,
              create interactive quizzes and discover the information that matters.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-3">
              <button
                type="button"
                onClick={handleOpenApp}
                className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-6 py-3.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold shadow-lg shadow-brand-600/25 transition-all focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:focus:ring-offset-slate-950"
              >
                <span>Try PaperPilot</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                type="button"
                onClick={() => scrollToSection('features')}
                className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-6 py-3.5 rounded-xl bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 text-sm font-semibold transition-all focus:outline-none focus:ring-2 focus:ring-brand-500/40"
              >
                <span>Explore Features</span>
              </button>
            </div>

            {/* Real Supported Scope Pills */}
            <div className="mt-7 flex flex-wrap items-center justify-center lg:justify-start gap-2 text-xs text-slate-500 dark:text-slate-400">
              <span className="px-2.5 py-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium">
                PDF • DOCX • TXT
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium">
                Source-Grounded Citations
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-medium">
                8 Document Categories
              </span>
            </div>
          </div>

          <div className="lg:col-span-7 animate-float-slow">
            <HeroProductPreview />
          </div>
        </div>
      </section>

      {/* Section 3: What is PaperPilot? */}
      <section
        id="about"
        className="scroll-mt-16 py-16 md:py-20 border-y border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 transition-colors duration-200"
      >
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <span className="text-xs font-bold uppercase tracking-widest text-brand-600 dark:text-brand-400">
            About PaperPilot
          </span>
          <h2 className="mt-2 text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white">
            What is PaperPilot?
          </h2>
          <p className="mt-4 text-sm sm:text-base text-slate-600 dark:text-slate-300 leading-relaxed max-w-3xl mx-auto">
            PaperPilot is an AI-powered document intelligence platform built to help you understand,
            analyse, and interact directly with your documents instead of manually searching through
            pages. Upload textbooks, research papers, meeting notes, financial or business reports,
            technical manuals, and legal agreements—PaperPilot indexes their contents and unlocks
            focused tools matched to what each file actually contains.
          </p>

          <div className="mt-10 grid grid-cols-2 sm:grid-cols-4 gap-3 text-left">
            {[
              'Educational Material',
              'Research Papers',
              'Business Reports',
              'Meeting Notes',
              'Legal Documents',
              'Financial Reports',
              'Technical Manuals',
              'General Documents',
            ].map((cat) => (
              <div
                key={cat}
                className="flex items-center space-x-2 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/70 border border-slate-200/80 dark:border-slate-700/80 text-xs font-semibold text-slate-700 dark:text-slate-200"
              >
                <FileText className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400 flex-shrink-0" />
                <span className="truncate">{cat}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Section 4: Features */}
      <section id="features" className="scroll-mt-16 py-16 md:py-24 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <span className="text-xs font-bold uppercase tracking-widest text-brand-600 dark:text-brand-400">
            Capabilities
          </span>
          <h2 className="mt-2 text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white">
            Built for Deep Understanding
          </h2>
          <p className="mt-3 text-sm sm:text-base text-slate-600 dark:text-slate-300">
            Every capability maps directly to grounded document extraction, vector retrieval, and structured synthesis.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {featureCards.map((feat) => {
            const Icon = feat.Icon;
            return (
              <div
                key={feat.title}
                className="group relative bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm hover:shadow-md hover:border-brand-300 dark:hover:border-brand-700 transition-all"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className={`w-11 h-11 rounded-xl border flex items-center justify-center ${feat.accent}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  {feat.upcoming && (
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-800">
                      Upcoming Feature
                    </span>
                  )}
                </div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">{feat.title}</h3>
                <p className="mt-2 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                  {feat.description}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Section 5: How It Works */}
      <section
        id="how-it-works"
        className="scroll-mt-16 py-16 md:py-24 border-y border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 transition-colors duration-200"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-12">
            <span className="text-xs font-bold uppercase tracking-widest text-brand-600 dark:text-brand-400">
              Workflow
            </span>
            <h2 className="mt-2 text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white">
              How It Works
            </h2>
            <p className="mt-3 text-sm sm:text-base text-slate-600 dark:text-slate-300">
              Automatic document processing runs from upload to indexed search in three straightforward steps.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {workflowSteps.map((item) => {
              const Icon = item.Icon;
              return (
                <div
                  key={item.step}
                  className="relative bg-slate-50 dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 transition-colors"
                >
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-2xl font-extrabold text-brand-600/80 dark:text-brand-400/90 font-mono">
                      {item.step}
                    </span>
                    <div className="w-10 h-10 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center text-brand-600 dark:text-brand-400 shadow-xs">
                      <Icon className="w-5 h-5" />
                    </div>
                  </div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    {item.step} – {item.title}
                  </h3>
                  <p className="mt-2 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                    {item.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Section 6: Why PaperPilot? */}
      <section className="py-16 md:py-24 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
          <div className="lg:col-span-5">
            <span className="text-xs font-bold uppercase tracking-widest text-brand-600 dark:text-brand-400">
              Why PaperPilot?
            </span>
            <h2 className="mt-2 text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white leading-tight">
              Designed for accuracy, clarity, and multi-format intelligence.
            </h2>
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              Rather than scattering PDFs, notes, and summaries across disconnected tools, PaperPilot keeps extraction, retrieval, and interactive study aligned inside a single workspace.
            </p>
          </div>

          <div className="lg:col-span-7 space-y-3.5">
            {whyPillars.map((pillar) => {
              const Icon = pillar.Icon;
              return (
                <div
                  key={pillar.title}
                  className="flex items-start space-x-4 p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xs"
                >
                  <div className="w-9 h-9 rounded-xl bg-brand-50 dark:bg-brand-950/70 text-brand-600 dark:text-brand-400 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Icon className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">{pillar.title}</h3>
                    <p className="mt-1 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                      {pillar.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Section 7: Final CTA */}
      <section className="px-4 sm:px-6 lg:px-8 pb-20 max-w-5xl mx-auto">
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 via-brand-700 to-indigo-700 dark:from-brand-700 dark:via-indigo-800 dark:to-slate-900 border border-brand-500/30 p-8 sm:p-12 text-center text-white shadow-xl">
          <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight">
            Make Every Document More Useful.
          </h2>
          <p className="mt-3 text-sm sm:text-base text-brand-100 max-w-xl mx-auto">
            Your next document could become your next big insight.
          </p>
          <div className="mt-7">
            <button
              type="button"
              onClick={handleOpenApp}
              className="inline-flex items-center space-x-2 px-7 py-3.5 rounded-xl bg-white text-brand-700 hover:bg-brand-50 text-sm font-bold shadow-md transition-all focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-brand-700"
            >
              <span>Try PaperPilot →</span>
            </button>
          </div>
        </div>
      </section>

      {/* Section 8: Footer */}
      <footer className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 py-10 px-4 sm:px-6 lg:px-8 transition-colors">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="max-w-sm">
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center text-white">
                <BookOpen className="w-4 h-4" />
              </div>
              <span className="text-base font-bold text-slate-900 dark:text-white">PaperPilot</span>
            </div>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              AI-powered document intelligence for chatting, summarizing, quizzing, and extracting structured knowledge from your files.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-6 text-xs font-medium text-slate-600 dark:text-slate-300">
            <button
              type="button"
              onClick={() => scrollToSection('features')}
              className="hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
            >
              Features
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('how-it-works')}
              className="hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
            >
              How It Works
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('about')}
              className="hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
            >
              About
            </button>
            <button
              type="button"
              onClick={handleOpenApp}
              className="text-brand-600 dark:text-brand-400 font-semibold hover:underline"
            >
              Open Workspace
            </button>
          </div>
        </div>

        <div className="max-w-7xl mx-auto mt-8 pt-6 border-t border-slate-200/80 dark:border-slate-800/80 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-400 dark:text-slate-500">
          <span>© {new Date().getFullYear()} PaperPilot. All rights reserved.</span>
          <span>Supports PDF, DOCX, and TXT documents.</span>
        </div>
      </footer>
    </div>
  );
};

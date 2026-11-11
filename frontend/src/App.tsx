import React, { useState, useEffect } from 'react';
import { Navbar, ActiveTab } from './components/Navbar';
import { DocumentUpload } from './components/DocumentUpload';
import { DocumentSidebar } from './components/DocumentSidebar';
import { ChatView } from './components/ChatView';
import { SummaryView } from './components/SummaryView';
import { QuizView } from './components/QuizView';
import { RevisionNotesView } from './components/RevisionNotesView';
import { AdaptiveInsightsView, ExamIntelligencePlaceholder } from './components/AdaptiveInsightsView';
import { LandingPage } from './components/LandingPage';
import { LoginPage, RegisterPage, ForgotPasswordPage, ResetPasswordPage } from './components/AuthPages';
import { useRouter } from './context/RouterContext';
import { useAuth } from './context/AuthContext';
import { DocumentItem, DocumentCategory, DOCUMENT_CATEGORIES } from './types';
import { documentApi } from './api/client';
import { Sparkles, Tag, Loader2, X, UploadCloud, FileText, Clock } from 'lucide-react';

const DashboardWorkspace: React.FC = () => {
  const { user, logout } = useAuth();
  const { navigate } = useRouter();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>('chat');
  const [isUpdatingCategory, setIsUpdatingCategory] = useState(false);
  const [isLoadingLibrary, setIsLoadingLibrary] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Fetch initial documents list scoped strictly to the authenticated user
  const loadDocuments = async () => {
    try {
      setIsLoadingLibrary(true);
      const docs = await documentApi.list();
      setDocuments(docs);
      setSelectedDocument((prev) => {
        if (prev && docs.some((d) => d.id === prev.id)) return prev;
        return docs.length > 0 ? docs[0] : null;
      });
    } catch (err) {
      console.error('Failed to load documents', err);
    } finally {
      setIsLoadingLibrary(false);
    }
  };

  useEffect(() => {
    setDocuments([]);
    setSelectedDocument(null);
    if (user?.id) {
      loadDocuments();
    }
  }, [user?.id]);

  const handleLogout = async () => {
    setDocuments([]);
    setSelectedDocument(null);
    await logout();
    navigate('/login');
  };

  const triggerUploadPicker = () => {
    const inputEl = window.document.getElementById('paperpilot-file-upload-input') as HTMLInputElement | null;
    if (inputEl) {
      inputEl.click();
    } else {
      setMobileSidebarOpen(true);
    }
  };

  // Ensure activeTab remains valid whenever selected document or category changes
  useEffect(() => {
    if (!selectedDocument) return;
    const cat = selectedDocument.document_category || 'General Document';
    const isEdu = cat === 'Educational Material';
    if (!isEdu && ['summary', 'quiz', 'revision', 'exam_placeholder'].includes(activeTab)) {
      setActiveTab('insights');
    } else if (isEdu && activeTab === 'insights') {
      setActiveTab('summary');
    }
  }, [selectedDocument?.id, selectedDocument?.document_category]);

  const isProcessing = (status: string) =>
    ['uploaded', 'extracting', 'embedding', 'indexing', 'processing'].includes(status);

  // Poll documents list if any document is currently in active processing
  useEffect(() => {
    const hasActiveProcessing = documents.some((d) => isProcessing(d.status));
    if (!hasActiveProcessing) return;

    const interval = setInterval(async () => {
      try {
        const updatedDocs = await documentApi.list();
        setDocuments(updatedDocs);
        if (selectedDocument) {
          const freshSelected = updatedDocs.find((d) => d.id === selectedDocument.id);
          if (freshSelected) {
            setSelectedDocument(freshSelected);
          }
        }
      } catch (err) {
        console.error('Error polling documents status:', err);
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [documents, selectedDocument]);

  const handleUploadSuccess = (newDoc: DocumentItem) => {
    setDocuments((prev) => [newDoc, ...prev]);
    setSelectedDocument(newDoc);
    setActiveTab('chat');
    setMobileSidebarOpen(false);
  };

  const handleReprocessDocument = async (id: string) => {
    try {
      const updated = await documentApi.reprocess(id);
      setDocuments((prev) => prev.map((d) => (d.id === id ? updated : d)));
      if (selectedDocument?.id === id) {
        setSelectedDocument(updated);
      }
    } catch (err) {
      console.error('Failed to reprocess document', err);
    }
  };

  const handleDeleteDocument = async (id: string) => {
    try {
      await documentApi.delete(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      if (selectedDocument?.id === id) {
        const remaining = documents.filter((d) => d.id !== id);
        setSelectedDocument(remaining.length > 0 ? remaining[0] : null);
      }
    } catch (err) {
      console.error('Failed to delete document', err);
    }
  };

  const handleCategoryOverride = async (newCategory: DocumentCategory) => {
    if (!selectedDocument || isUpdatingCategory) return;
    try {
      setIsUpdatingCategory(true);
      const updated = await documentApi.updateCategory(selectedDocument.id, newCategory);
      setDocuments((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setSelectedDocument(updated);
    } catch (err) {
      console.error('Failed to update document category', err);
    } finally {
      setIsUpdatingCategory(false);
    }
  };

  const currentCategory = (selectedDocument?.document_category || 'General Document') as DocumentCategory;
  const isEducational = currentCategory === 'Educational Material';
  const currentFormat = (selectedDocument?.file_format || 'pdf').toUpperCase();
  const unitName = selectedDocument?.citation_unit === 'section' ? 'sections' : 'pages';

  return (
    <div className="relative flex flex-col h-full w-full overflow-hidden bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors duration-200 print:h-auto print:overflow-visible print:bg-white print:text-black">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        hasSelectedDocument={!!selectedDocument}
        documentCategory={selectedDocument ? currentCategory : undefined}
        onToggleMobileSidebar={() => setMobileSidebarOpen((prev) => !prev)}
        userName={user?.name}
        userEmail={user?.email}
        onLogout={handleLogout}
      />

      <div className="relative flex-1 flex min-h-0 min-w-0 overflow-hidden print:block print:overflow-visible">
        {/* Mobile Backdrop */}
        {mobileSidebarOpen && (
          <div
            onClick={() => setMobileSidebarOpen(false)}
            className="fixed inset-0 bg-slate-950/50 z-30 lg:hidden print:hidden"
          />
        )}

        {/* Left Sidebar (Dock on lg+, Drawer on < lg) */}
        <aside
          className={`${
            mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
          } fixed lg:relative inset-y-0 left-0 z-40 lg:z-auto w-80 max-w-[85vw] border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col flex-shrink-0 min-h-0 overflow-hidden transition-transform duration-200 ease-out print:hidden`}
        >
          <div className="lg:hidden flex items-center justify-between px-4 py-2.5 border-b border-slate-200 dark:border-slate-800">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Document Library
            </span>
            <button
              type="button"
              onClick={() => setMobileSidebarOpen(false)}
              aria-label="Close library"
              className="p-1 rounded-lg text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <DocumentUpload onUploadSuccess={handleUploadSuccess} />
          <DocumentSidebar
            documents={documents}
            selectedDocument={selectedDocument}
            onSelectDocument={(doc) => {
              setSelectedDocument(doc);
              setMobileSidebarOpen(false);
            }}
            onDeleteDocument={handleDeleteDocument}
          />
        </aside>

        {/* Main Content Workspace */}
        <div className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden relative print:block print:overflow-visible">
          {/* Document Classification & Metadata Bar */}
          {selectedDocument && (
            <div className="flex-shrink-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-4 sm:px-5 py-2 flex flex-wrap items-center justify-between gap-2 text-xs transition-colors print:hidden">
              <div className="flex items-center space-x-2 min-w-0">
                <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
                  {currentFormat}
                </span>
                <span
                  className="font-semibold text-slate-700 dark:text-slate-200 truncate max-w-[160px] sm:max-w-xs"
                  title={selectedDocument.original_filename}
                >
                  {selectedDocument.original_filename}
                </span>
                {selectedDocument.status === 'ready' && (
                  <span className="text-[11px] text-slate-400 dark:text-slate-400 hidden sm:inline">
                    • {selectedDocument.total_pages} {unitName} • {selectedDocument.total_chunks || 0} chunks
                  </span>
                )}
              </div>

              <div className="flex items-center space-x-2 flex-shrink-0">
                <span
                  className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center space-x-1"
                  title={selectedDocument.classification_reason || 'Detected document category'}
                >
                  <Tag className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
                  <span className="hidden md:inline">Category:</span>
                </span>
                <select
                  aria-label="Document Category"
                  value={currentCategory}
                  disabled={isUpdatingCategory || isProcessing(selectedDocument.status)}
                  onChange={(e) => handleCategoryOverride(e.target.value as DocumentCategory)}
                  className="text-xs font-semibold bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 disabled:opacity-60"
                >
                  {DOCUMENT_CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
                {isUpdatingCategory ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-600 dark:text-brand-400" />
                ) : (
                  <span
                    className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-950/70 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800/70"
                    title={selectedDocument.classification_reason || ''}
                  >
                    {selectedDocument.classification_source === 'manual'
                      ? 'Manual'
                      : `${Math.round((selectedDocument.classification_confidence || 0) * 100)}% conf.`}
                  </span>
                )}
              </div>
            </div>
          )}

          <main className="flex-1 flex min-h-0 min-w-0 overflow-hidden relative print:block print:overflow-visible">
            {selectedDocument ? (
              <>
                {activeTab === 'chat' && (
                  <ChatView
                    document={selectedDocument}
                    onReprocess={() => handleReprocessDocument(selectedDocument.id)}
                  />
                )}
                {isEducational && activeTab === 'summary' && <SummaryView document={selectedDocument} />}
                {isEducational && activeTab === 'quiz' && <QuizView document={selectedDocument} />}
                {isEducational && activeTab === 'revision' && <RevisionNotesView document={selectedDocument} />}
                {isEducational && activeTab === 'exam_placeholder' && (
                  <ExamIntelligencePlaceholder document={selectedDocument} />
                )}
                {!isEducational && activeTab === 'insights' && (
                  <AdaptiveInsightsView
                    document={selectedDocument}
                    onSwitchToChat={() => setActiveTab('chat')}
                  />
                )}
              </>
            ) : isLoadingLibrary ? (
              <div className="flex-1 flex items-center justify-center p-6">
                <div className="flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400">
                  <Loader2 className="w-5 h-5 animate-spin text-brand-600 dark:text-brand-400" />
                  <span>Loading your private workspace...</span>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center p-6 sm:p-8 overflow-y-auto">
                <div className="max-w-xl w-full text-center">
                  <div className="w-16 h-16 rounded-3xl bg-brand-50 dark:bg-brand-950 text-brand-600 dark:text-brand-400 flex items-center justify-center mx-auto mb-4 shadow-sm border border-brand-100 dark:border-brand-900">
                    <Sparkles className="w-8 h-8" />
                  </div>
                  <h2 className="text-xl sm:text-2xl font-bold text-slate-800 dark:text-white">
                    Welcome{user?.name ? `, ${user.name}` : ''} to PaperPilot
                  </h2>
                  <p className="text-sm text-slate-600 dark:text-slate-300 mt-2 leading-relaxed">
                    Your workspace is ready. Upload your first document to get started.
                  </p>

                  <div className="mt-6">
                    <button
                      type="button"
                      onClick={triggerUploadPicker}
                      className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold shadow-sm transition-all"
                    >
                      <UploadCloud className="w-4 h-4" />
                      <span>Upload Document</span>
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-7 text-left">
                    <div className="p-3.5 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-xs">
                      <div className="flex items-center space-x-1.5 text-slate-500 dark:text-slate-400 mb-1">
                        <FileText className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
                        <span className="text-[11px] font-semibold uppercase tracking-wider">Total documents</span>
                      </div>
                      <p className="text-lg font-bold text-slate-800 dark:text-white">0</p>
                    </div>
                    <div className="p-3.5 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-xs">
                      <div className="flex items-center space-x-1.5 text-slate-500 dark:text-slate-400 mb-1">
                        <FileText className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
                        <span className="text-[11px] font-semibold uppercase tracking-wider">Recent documents</span>
                      </div>
                      <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">Empty</p>
                    </div>
                    <div className="p-3.5 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-xs">
                      <div className="flex items-center space-x-1.5 text-slate-500 dark:text-slate-400 mb-1">
                        <Clock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                        <span className="text-[11px] font-semibold uppercase tracking-wider">Recent activity</span>
                      </div>
                      <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">Empty</p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  const { pathname, isAppRoute, navigate } = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    if (isAppRoute && !isAuthenticated) {
      navigate('/login');
    } else if ((pathname === '/login' || pathname === '/register') && isAuthenticated) {
      navigate('/app');
    }
  }, [isAppRoute, pathname, isAuthenticated, isLoading, navigate]);

  if (pathname === '/login') {
    if (isAuthenticated) return null;
    return <LoginPage />;
  }
  if (pathname === '/register') {
    if (isAuthenticated) return null;
    return <RegisterPage />;
  }
  if (pathname === '/forgot-password') {
    return <ForgotPasswordPage />;
  }
  if (pathname === '/reset-password') {
    return <ResetPasswordPage />;
  }

  if (isAppRoute) {
    if (isLoading || !isAuthenticated) {
      return (
        <div className="h-full w-full flex items-center justify-center bg-slate-50 dark:bg-slate-950 text-slate-600 dark:text-slate-300">
          <div className="flex items-center space-x-2.5 text-sm font-medium">
            <Loader2 className="w-5 h-5 animate-spin text-brand-600 dark:text-brand-400" />
            <span>Verifying session...</span>
          </div>
        </div>
      );
    }
    return <DashboardWorkspace />;
  }

  return <LandingPage />;
};

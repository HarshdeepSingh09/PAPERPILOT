import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { DocumentUpload } from './components/DocumentUpload';
import { DocumentSidebar } from './components/DocumentSidebar';
import { ChatView } from './components/ChatView';
import { SummaryView } from './components/SummaryView';
import { QuizView } from './components/QuizView';
import { RevisionNotesView } from './components/RevisionNotesView';
import { DocumentItem } from './types';
import { documentApi } from './api/client';
import { BookOpen, Sparkles, Layers, Zap } from 'lucide-react';

export const App: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null);
  const [activeTab, setActiveTab] = useState<'chat' | 'summary' | 'quiz' | 'revision'>('chat');

  // Fetch initial documents list
  const loadDocuments = async () => {
    try {
      const docs = await documentApi.list();
      setDocuments(docs);
      if (docs.length > 0 && !selectedDocument) {
        setSelectedDocument(docs[0]);
      }
    } catch (err) {
      console.error('Failed to load documents', err);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

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

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-slate-50">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        hasSelectedDocument={!!selectedDocument}
      />

      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <aside className="w-80 border-r border-slate-200 bg-white flex flex-col flex-shrink-0">
          <DocumentUpload onUploadSuccess={handleUploadSuccess} />
          <DocumentSidebar
            documents={documents}
            selectedDocument={selectedDocument}
            onSelectDocument={setSelectedDocument}
            onDeleteDocument={handleDeleteDocument}
          />
        </aside>

        {/* Main Content Workspace */}
        <main className="flex-1 flex overflow-hidden">
          {selectedDocument ? (
            <>
              {activeTab === 'chat' && (
                <ChatView
                  document={selectedDocument}
                  onReprocess={() => handleReprocessDocument(selectedDocument.id)}
                />
              )}
              {activeTab === 'summary' && <SummaryView document={selectedDocument} />}
              {activeTab === 'quiz' && <QuizView document={selectedDocument} />}
              {activeTab === 'revision' && <RevisionNotesView document={selectedDocument} />}
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center p-8">
              <div className="max-w-md text-center">
                <div className="w-16 h-16 rounded-3xl bg-brand-50 text-brand-600 flex items-center justify-center mx-auto mb-4 shadow-sm">
                  <Sparkles className="w-8 h-8" />
                </div>
                <h2 className="text-xl font-bold text-slate-800">
                  Welcome to PaperPilot
                </h2>
                <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                  Upload a PDF using the left panel to begin chatting with page citations, generating summaries, or testing yourself with AI-generated quizzes and revision notes.
                </p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6 text-left">
                  <div className="p-3 bg-white rounded-xl border border-slate-200">
                    <Sparkles className="w-4 h-4 text-brand-600 mb-1" />
                    <h4 className="text-[11px] font-bold text-slate-700">RAG Chat</h4>
                    <p className="text-[10px] text-slate-400 mt-0.5">Page citations</p>
                  </div>
                  <div className="p-3 bg-white rounded-xl border border-slate-200">
                    <BookOpen className="w-4 h-4 text-indigo-600 mb-1" />
                    <h4 className="text-[11px] font-bold text-slate-700">Summaries</h4>
                    <p className="text-[10px] text-slate-400 mt-0.5">Key takeaways</p>
                  </div>
                  <div className="p-3 bg-white rounded-xl border border-slate-200">
                    <Layers className="w-4 h-4 text-emerald-600 mb-1" />
                    <h4 className="text-[11px] font-bold text-slate-700">Quizzes</h4>
                    <p className="text-[10px] text-slate-400 mt-0.5">Interactive MCQs</p>
                  </div>
                  <div className="p-3 bg-white rounded-xl border border-slate-200">
                    <Zap className="w-4 h-4 text-rose-500 mb-1" />
                    <h4 className="text-[11px] font-bold text-slate-700">Revision</h4>
                    <p className="text-[10px] text-slate-400 mt-0.5">High-yield notes</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

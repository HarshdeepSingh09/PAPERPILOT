import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import {
  Send,
  Bot,
  User,
  Bookmark,
  Loader2,
  Sparkles,
  Trash2,
  HelpCircle,
  AlertCircle,
  CheckCircle2,
  RefreshCw
} from 'lucide-react';
import { DocumentItem, ChatMessage } from '../types';
import { chatApi } from '../api/client';
import { PDFViewer } from './PDFViewer';

interface ChatViewProps {
  document: DocumentItem;
  onReprocess?: () => void;
}

export const ChatView: React.FC<ChatViewProps> = ({ document, onReprocess }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [targetPage, setTargetPage] = useState<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  const isProcessing = ['uploaded', 'extracting', 'embedding', 'indexing', 'processing'].includes(document.status);
  const isReady = document.status === 'ready';

  // Load conversation history on document change if ready
  useEffect(() => {
    if (!isReady) {
      setMessages([]);
      return;
    }

    let isMounted = true;
    const fetchHistory = async () => {
      try {
        setIsHistoryLoading(true);
        const history = await chatApi.getHistory(document.id);
        if (isMounted) {
          setMessages(history);
        }
      } catch (err) {
        console.error('Failed to load chat history', err);
      } finally {
        if (isMounted) setIsHistoryLoading(false);
      }
    };
    fetchHistory();
    return () => {
      isMounted = false;
    };
  }, [document.id, isReady]);

  // Scroll only the message thread container to bottom on new messages or loading state
  useEffect(() => {
    const container = chatScrollRef.current;
    if (!container) return;
    container.scrollTo({
      top: container.scrollHeight,
      behavior: isLoading ? 'smooth' : 'auto',
    });
  }, [messages, isLoading]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading || !isReady) return;

    const userQuery = input.trim();
    setInput('');

    // Optimistic user message
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: userQuery,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setIsLoading(true);

    try {
      const response = await chatApi.sendMessage(document.id, userQuery);
      setMessages((prev) => [...prev, response]);
    } catch (err: any) {
      console.error('Failed to send message', err);
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'Failed to reach backend API. Make sure the FastAPI server is running.';
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ ${detail}`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearChat = async () => {
    if (!confirm('Are you sure you want to clear conversation history for this document?')) {
      return;
    }
    try {
      setIsClearing(true);
      await chatApi.clearHistory(document.id);
      setMessages([]);
    } catch (err: any) {
      console.error('Failed to clear history:', err);
      alert('Failed to clear chat history: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setIsClearing(false);
    }
  };

  const handleAskStarter = (question: string) => {
    setInput(question);
  };

  const getStepStatus = (stepKey: string) => {
    const order = ['uploaded', 'extracting', 'embedding', 'indexing', 'ready'];
    const currentIndex = order.indexOf(document.status);
    const stepIndex = order.indexOf(stepKey);

    if (currentIndex > stepIndex || document.status === 'ready') return 'completed';
    if (currentIndex === stepIndex) return 'active';
    return 'pending';
  };

  const getStarterQuestions = (): string[] => {
    const cat = document.document_category || 'General Document';
    switch (cat) {
      case 'Educational Material':
        return [
          'What is the chapter or topic title?',
          'Summarize the main concepts covered in this document.',
          'List the key definitions and formulas mentioned.',
        ];
      case 'Research Paper':
        return [
          'What is the main research objective of this paper?',
          'What methodology and datasets were used?',
          'What are the key findings and limitations?',
        ];
      case 'Business Report':
        return [
          'Provide an executive summary of this report.',
          'What key metrics or figures are reported?',
          'What strategic recommendations and action items are stated?',
        ];
      case 'Meeting Notes':
        return [
          'Summarize the main decisions agreed in this meeting.',
          'List all action items and assigned responsibilities.',
          'What deadlines or unresolved issues are mentioned?',
        ];
      case 'Legal Document':
        return [
          'What is the overview and who are the parties involved?',
          'Summarize the key clauses and party obligations.',
          'What effective dates, deadlines, or conditions apply?',
        ];
      case 'Financial Report':
        return [
          'Summarize the financial performance reported in this document.',
          'What revenue and expense figures are disclosed?',
          'What financial trends or ratios are mentioned?',
        ];
      case 'User Manual / Technical Documentation':
        return [
          'What system or workflow does this documentation cover?',
          'List the setup steps and important instructions.',
          'What warnings or troubleshooting guidance are provided?',
        ];
      default:
        return [
          'What is this document about?',
          'Summarize the key points covered.',
          'List the most important details or facts mentioned.',
        ];
    }
  };

  const citationUnitLabel = (document.citation_unit || ((document.file_format || 'pdf') === 'pdf' ? 'page' : 'section')) === 'section' ? 'sections' : 'pages';

  return (
    <div className="flex-1 flex flex-col md:flex-row min-h-0 min-w-0 overflow-hidden">
      {/* Left: Embedded PDF / Document Section Viewer with Target Page Jumping */}
      <PDFViewer document={document} targetPage={targetPage} />

      {/* Right: Contextual Chat Panel */}
      <div className="w-full md:w-1/2 h-1/2 md:h-full flex flex-col min-h-0 overflow-hidden bg-white dark:bg-slate-900 md:border-l border-slate-200 dark:border-slate-800">
        {/* Chat Header */}
        <div className="flex-shrink-0 p-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/70 dark:bg-slate-900">
          <div>
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 flex items-center space-x-1.5">
              <Sparkles className="w-4 h-4 text-brand-600 dark:text-brand-400" />
              <span>Contextual Q&A</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Answers grounded in document with verified citations
            </p>
          </div>

          {messages.length > 0 && isReady && (
            <button
              type="button"
              onClick={handleClearChat}
              disabled={isClearing || isLoading}
              className="px-2.5 py-1 text-xs text-slate-500 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/50 border border-slate-200 dark:border-slate-700 hover:border-red-200 dark:hover:border-red-800 rounded-lg transition-colors flex items-center space-x-1"
              title="Clear conversation history for this document"
            >
              {isClearing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
              <span className="hidden sm:inline">Clear Chat</span>
            </button>
          )}
        </div>

        {/* Message Thread Area */}
        <div ref={chatScrollRef} className="relative flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
          {/* Status 1: Active Processing Stepper */}
          {isProcessing ? (
            <div className="py-8 px-6 max-w-md mx-auto">
              <div className="text-center mb-6">
                <div className="w-12 h-12 bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 rounded-2xl flex items-center justify-center mx-auto mb-3 shadow-sm border border-brand-100 dark:border-brand-900">
                  <Loader2 className="w-6 h-6 animate-spin text-brand-600 dark:text-brand-400" />
                </div>
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">Automatic Document Processing</h3>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                  Extracting content, generating embeddings, and building the vector index.
                </p>
              </div>

              <div className="bg-slate-50 dark:bg-slate-800/70 border border-slate-200 dark:border-slate-700 rounded-2xl p-4 space-y-3">
                {[
                  { key: 'uploaded', label: '1. File Upload & Validation' },
                  { key: 'extracting', label: '2. Extraction & Classification' },
                  { key: 'embedding', label: '3. Gemini Embeddings Generation' },
                  { key: 'indexing', label: '4. ChromaDB Vector Indexing' },
                ].map((step) => {
                  const s = getStepStatus(step.key);
                  return (
                    <div key={step.key} className="flex items-center space-x-3 text-xs">
                      {s === 'completed' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                      ) : s === 'active' ? (
                        <Loader2 className="w-4 h-4 text-brand-600 dark:text-brand-400 animate-spin flex-shrink-0" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border border-slate-300 dark:border-slate-600 flex-shrink-0" />
                      )}
                      <span
                        className={`font-medium ${
                          s === 'completed'
                            ? 'text-slate-700 dark:text-slate-200'
                            : s === 'active'
                            ? 'text-brand-700 dark:text-brand-300 font-semibold'
                            : 'text-slate-400 dark:text-slate-500'
                        }`}
                      >
                        {step.label}
                      </span>
                    </div>
                  );
                })}
              </div>

              <p className="text-center text-[11px] text-slate-400 dark:text-slate-500 mt-4">
                Chat and page citations will be enabled automatically once ready.
              </p>
            </div>
          ) : document.status === 'ocr_required' ? (
            /* Status 2: Scanned Document Warning */
            <div className="text-center py-12 px-6 max-w-md mx-auto">
              <div className="w-12 h-12 bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 rounded-2xl flex items-center justify-center mx-auto mb-3 border border-amber-200 dark:border-amber-800/60">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">Scanned Document Detected</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
                This PDF contains scanned images without extractable digital text.
                OCR (Optical Character Recognition) is not yet supported.
              </p>
              <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-950/40 rounded-xl border border-amber-200 dark:border-amber-800/60 text-xs text-amber-800 dark:text-amber-200 text-left">
                <strong>Notice:</strong> Document chat, vector search, and summaries require extractable text and are disabled for image-only files.
              </div>
            </div>
          ) : document.status === 'failed' ? (
            /* Status 3: Processing Failed Alert */
            <div className="text-center py-12 px-6 max-w-md mx-auto">
              <div className="w-12 h-12 bg-red-50 dark:bg-red-950/60 text-red-600 dark:text-red-400 rounded-2xl flex items-center justify-center mx-auto mb-3 border border-red-200 dark:border-red-800/60">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">Document Processing Failed</h3>
              <p className="text-xs text-red-600 dark:text-red-300 mt-2 leading-relaxed bg-red-50 dark:bg-red-950/40 p-3 rounded-xl border border-red-200 dark:border-red-800/60">
                {document.error_message || 'An error occurred during automatic processing.'}
              </p>
              {onReprocess && (
                <button
                  type="button"
                  onClick={onReprocess}
                  className="mt-4 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-semibold shadow-sm inline-flex items-center space-x-1.5 transition-all"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Retry Automatic Processing</span>
                </button>
              )}
            </div>
          ) : isHistoryLoading ? (
            <div className="flex items-center justify-center py-12 text-slate-400 dark:text-slate-500">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              <span className="text-xs">Loading chat history...</span>
            </div>
          ) : messages.length === 0 ? (
            /* Status 4: Ready with Starter Questions */
            <div className="text-center py-12 px-6">
              <div className="w-12 h-12 bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 rounded-2xl flex items-center justify-center mx-auto mb-3 shadow-sm">
                <Bot className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">Ready to examine this document</h3>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 max-w-sm mx-auto">
                Ask questions grounded strictly in the uploaded file. Answers cite exact {citationUnitLabel}.
              </p>

              {/* Starter Questions */}
              <div className="mt-6 flex flex-col gap-2 max-w-sm mx-auto text-left">
                <span className="text-[11px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider flex items-center">
                  <HelpCircle className="w-3 h-3 mr-1" /> Suggested questions:
                </span>
                {getStarterQuestions().map((q, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleAskStarter(q)}
                    className="p-2 text-xs bg-slate-50 dark:bg-slate-800/80 hover:bg-brand-50 dark:hover:bg-brand-950/60 hover:text-brand-700 dark:hover:text-brand-300 text-slate-600 dark:text-slate-300 rounded-lg border border-slate-200 dark:border-slate-700 transition-colors text-left"
                  >
                    "{q}"
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Active Message Thread */
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex items-start space-x-3 ${
                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-xl bg-brand-600 text-white flex items-center justify-center flex-shrink-0 shadow-sm mt-0.5">
                    <Bot className="w-4 h-4" />
                  </div>
                )}

                <div
                  className={`max-w-[80%] rounded-2xl p-3.5 text-xs leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-brand-600 text-white rounded-tr-none'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 rounded-tl-none border border-slate-200/60 dark:border-slate-700 shadow-sm'
                  }`}
                >
                  <div className="text-xs leading-relaxed break-words space-y-2">
                    {msg.role === 'user' ? (
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                        components={{
                          p: ({ node, ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props} />,
                          ul: ({ node, ...props }) => <ul className="list-disc list-inside space-y-1 my-2" {...props} />,
                          ol: ({ node, ...props }) => <ol className="list-decimal list-inside space-y-1 my-2" {...props} />,
                          li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
                          strong: ({ node, ...props }) => <strong className="font-semibold text-slate-900 dark:text-white" {...props} />,
                          h1: ({ node, ...props }) => <h1 className="text-sm font-bold text-slate-900 dark:text-white mt-3 mb-1" {...props} />,
                          h2: ({ node, ...props }) => <h2 className="text-xs font-bold text-slate-900 dark:text-white mt-2 mb-1" {...props} />,
                          h3: ({ node, ...props }) => <h3 className="text-xs font-semibold text-slate-900 dark:text-white mt-2 mb-1" {...props} />,
                          code: ({ node, inline, ...props }: any) =>
                            inline ? (
                              <code className="bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-100 px-1 py-0.5 rounded text-[11px] font-mono" {...props} />
                            ) : (
                              <pre className="bg-slate-900 dark:bg-slate-950 text-slate-100 p-2.5 rounded-lg text-[11px] font-mono overflow-x-auto my-2 border border-slate-700">
                                <code {...props} />
                              </pre>
                            ),
                          table: ({ node, ...props }) => (
                            <div className="overflow-x-auto my-2 border border-slate-200 dark:border-slate-700 rounded-lg">
                              <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700 text-left" {...props} />
                            </div>
                          ),
                          th: ({ node, ...props }) => <th className="px-2.5 py-1.5 bg-slate-200 dark:bg-slate-700 font-semibold text-slate-700 dark:text-slate-100 text-[11px]" {...props} />,
                          td: ({ node, ...props }) => <td className="px-2.5 py-1.5 border-t border-slate-200 dark:border-slate-700 text-[11px]" {...props} />,
                          blockquote: ({ node, ...props }) => (
                            <blockquote className="border-l-2 border-brand-500 pl-2.5 my-2 text-slate-600 dark:text-slate-300 italic bg-brand-50/50 dark:bg-brand-950/40 py-1 rounded-r" {...props} />
                          )
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    )}
                  </div>

                  {/* Citation Badges */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-slate-200 dark:border-slate-700 flex flex-wrap gap-1.5 items-center">
                      <span className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 dark:text-slate-500 mr-1 flex items-center">
                        <Bookmark className="w-3 h-3 mr-0.5 text-brand-600 dark:text-brand-400" /> Citations:
                      </span>
                      {msg.citations.map((c, i) => {
                        const unitName = c.source_type === 'section' || (document.file_format && document.file_format !== 'pdf') ? 'Section' : 'Page';
                        const badgeText = c.label || `${unitName} ${c.page}`;
                        return (
                          <button
                            key={i}
                            type="button"
                            onClick={() => setTargetPage(c.page)}
                            title={c.snippet ? `${badgeText}: ${c.snippet}` : `Jump to ${badgeText}`}
                            className="px-2 py-0.5 text-[11px] font-medium bg-brand-100 dark:bg-brand-950/70 hover:bg-brand-200 dark:hover:bg-brand-900 text-brand-800 dark:text-brand-300 rounded-md transition-colors"
                          >
                            {badgeText}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-xl bg-slate-800 dark:bg-slate-700 text-white flex items-center justify-center flex-shrink-0 shadow-sm mt-0.5">
                    <User className="w-4 h-4" />
                  </div>
                )}
              </div>
            ))
          )}

          {isLoading && (
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-xl bg-brand-600 text-white flex items-center justify-center flex-shrink-0 shadow-sm">
                <Bot className="w-4 h-4" />
              </div>
              <div className="bg-slate-100 dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700 rounded-2xl rounded-tl-none p-3.5 text-xs text-slate-500 dark:text-slate-400 flex items-center space-x-2">
                <Loader2 className="w-4 h-4 animate-spin text-brand-600 dark:text-brand-400" />
                <span>Searching ChromaDB & synthesizing response with Gemini...</span>
              </div>
            </div>
          )}

        </div>

        {/* Input Form */}
        <form
          onSubmit={handleSend}
          className="flex-shrink-0 p-3 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex space-x-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend(e);
              }
            }}
            placeholder={
              isProcessing
                ? `Processing document (${document.status})... Chat will be available once ready.`
                : document.status === 'ocr_required'
                ? 'Chat is unavailable for scanned image-only documents.'
                : document.status === 'failed'
                ? 'Chat is unavailable because document processing failed.'
                : 'Ask a question about this document... (Press Enter to send)'
            }
            disabled={isLoading || !isReady}
            className="flex-1 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl px-4 py-2.5 text-xs text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all disabled:bg-slate-100 dark:disabled:bg-slate-800/50 disabled:text-slate-400 dark:disabled:text-slate-600 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading || !isReady}
            className="px-4 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 dark:disabled:text-slate-600 text-white rounded-xl transition-all shadow-sm flex items-center justify-center cursor-pointer disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};

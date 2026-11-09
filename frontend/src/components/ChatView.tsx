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
  const chatBottomRef = useRef<HTMLDivElement>(null);

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

  // Scroll to bottom on new messages or loading state
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
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

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left: Embedded PDF Viewer with Target Page Jumping */}
      <PDFViewer document={document} targetPage={targetPage} />

      {/* Right: Contextual Chat Panel */}
      <div className="w-1/2 flex flex-col bg-white border-l border-slate-200">
        {/* Chat Header */}
        <div className="p-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50/70">
          <div>
            <h2 className="text-sm font-semibold text-slate-800 flex items-center space-x-1.5">
              <Sparkles className="w-4 h-4 text-brand-600" />
              <span>Contextual Q&A</span>
            </h2>
            <p className="text-xs text-slate-500">Answers grounded in document with verified citations</p>
          </div>

          {messages.length > 0 && isReady && (
            <button
              type="button"
              onClick={handleClearChat}
              disabled={isClearing || isLoading}
              className="px-2.5 py-1 text-xs text-slate-500 hover:text-red-600 hover:bg-red-50 border border-slate-200 hover:border-red-200 rounded-lg transition-colors flex items-center space-x-1"
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
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Status 1: Active Processing Stepper */}
          {isProcessing ? (
            <div className="py-8 px-6 max-w-md mx-auto">
              <div className="text-center mb-6">
                <div className="w-12 h-12 bg-brand-50 text-brand-600 rounded-2xl flex items-center justify-center mx-auto mb-3 shadow-sm border border-brand-100">
                  <Loader2 className="w-6 h-6 animate-spin text-brand-600" />
                </div>
                <h3 className="text-sm font-bold text-slate-800">Automatic Document Processing</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Extracting content, generating embeddings, and building the vector index.
                </p>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 space-y-3">
                {[
                  { key: 'uploaded', label: '1. PDF Upload & Validation' },
                  { key: 'extracting', label: '2. Text & Metadata Extraction' },
                  { key: 'embedding', label: '3. Gemini Embeddings Generation' },
                  { key: 'indexing', label: '4. ChromaDB Vector Indexing' },
                ].map((step) => {
                  const s = getStepStatus(step.key);
                  return (
                    <div key={step.key} className="flex items-center space-x-3 text-xs">
                      {s === 'completed' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                      ) : s === 'active' ? (
                        <Loader2 className="w-4 h-4 text-brand-600 animate-spin flex-shrink-0" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border border-slate-300 flex-shrink-0" />
                      )}
                      <span
                        className={`font-medium ${
                          s === 'completed'
                            ? 'text-slate-700'
                            : s === 'active'
                            ? 'text-brand-700 font-semibold'
                            : 'text-slate-400'
                        }`}
                      >
                        {step.label}
                      </span>
                    </div>
                  );
                })}
              </div>

              <p className="text-center text-[11px] text-slate-400 mt-4">
                Chat and page citations will be enabled automatically once ready.
              </p>
            </div>
          ) : document.status === 'ocr_required' ? (
            /* Status 2: Scanned Document Warning */
            <div className="text-center py-12 px-6 max-w-md mx-auto">
              <div className="w-12 h-12 bg-amber-50 text-amber-600 rounded-2xl flex items-center justify-center mx-auto mb-3 border border-amber-200">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-800">Scanned Document Detected</h3>
              <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                This PDF contains scanned images without extractable digital text.
                OCR (Optical Character Recognition) is not yet supported.
              </p>
              <div className="mt-4 p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-800 text-left">
                <strong>Notice:</strong> Document chat, vector search, and summaries require extractable text and are disabled for image-only files.
              </div>
            </div>
          ) : document.status === 'failed' ? (
            /* Status 3: Processing Failed Alert */
            <div className="text-center py-12 px-6 max-w-md mx-auto">
              <div className="w-12 h-12 bg-red-50 text-red-600 rounded-2xl flex items-center justify-center mx-auto mb-3 border border-red-200">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-800">Document Processing Failed</h3>
              <p className="text-xs text-red-600 mt-2 leading-relaxed bg-red-50 p-3 rounded-xl border border-red-200">
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
            <div className="flex items-center justify-center py-12 text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              <span className="text-xs">Loading chat history...</span>
            </div>
          ) : messages.length === 0 ? (
            /* Status 4: Ready with Starter Questions */
            <div className="text-center py-12 px-6">
              <div className="w-12 h-12 bg-brand-50 text-brand-600 rounded-2xl flex items-center justify-center mx-auto mb-3 shadow-sm">
                <Bot className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-700">Ready to examine this document</h3>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                Ask about key conclusions, equations, definitions, or experiments. Answers cite exact pages.
              </p>

              {/* Starter Questions */}
              <div className="mt-6 flex flex-col gap-2 max-w-sm mx-auto text-left">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center">
                  <HelpCircle className="w-3 h-3 mr-1" /> Suggested questions:
                </span>
                <button
                  type="button"
                  onClick={() => handleAskStarter('What is the chapter name?')}
                  className="p-2 text-xs bg-slate-50 hover:bg-brand-50 hover:text-brand-700 text-slate-600 rounded-lg border border-slate-200 transition-colors text-left"
                >
                  "What is the chapter name?"
                </button>
                <button
                  type="button"
                  onClick={() => handleAskStarter('What happens when magnesium ribbon is burned in air?')}
                  className="p-2 text-xs bg-slate-50 hover:bg-brand-50 hover:text-brand-700 text-slate-600 rounded-lg border border-slate-200 transition-colors text-left"
                >
                  "What happens when magnesium ribbon is burned in air?"
                </button>
                <button
                  type="button"
                  onClick={() => handleAskStarter('What is rancidity and how can it be prevented?')}
                  className="p-2 text-xs bg-slate-50 hover:bg-brand-50 hover:text-brand-700 text-slate-600 rounded-lg border border-slate-200 transition-colors text-left"
                >
                  "What is rancidity and how can it be prevented?"
                </button>
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
                      : 'bg-slate-100 text-slate-800 rounded-tl-none border border-slate-200/60 shadow-sm'
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
                          strong: ({ node, ...props }) => <strong className="font-semibold text-slate-900" {...props} />,
                          h1: ({ node, ...props }) => <h1 className="text-sm font-bold text-slate-900 mt-3 mb-1" {...props} />,
                          h2: ({ node, ...props }) => <h2 className="text-xs font-bold text-slate-900 mt-2 mb-1" {...props} />,
                          h3: ({ node, ...props }) => <h3 className="text-xs font-semibold text-slate-900 mt-2 mb-1" {...props} />,
                          code: ({ node, inline, ...props }: any) =>
                            inline ? (
                              <code className="bg-slate-200 text-slate-800 px-1 py-0.5 rounded text-[11px] font-mono" {...props} />
                            ) : (
                              <pre className="bg-slate-800 text-slate-100 p-2.5 rounded-lg text-[11px] font-mono overflow-x-auto my-2">
                                <code {...props} />
                              </pre>
                            ),
                          table: ({ node, ...props }) => (
                            <div className="overflow-x-auto my-2 border border-slate-200 rounded-lg">
                              <table className="min-w-full divide-y divide-slate-200 text-left" {...props} />
                            </div>
                          ),
                          th: ({ node, ...props }) => <th className="px-2.5 py-1.5 bg-slate-200 font-semibold text-slate-700 text-[11px]" {...props} />,
                          td: ({ node, ...props }) => <td className="px-2.5 py-1.5 border-t border-slate-200 text-[11px]" {...props} />,
                          blockquote: ({ node, ...props }) => (
                            <blockquote className="border-l-2 border-brand-500 pl-2.5 my-2 text-slate-600 italic bg-brand-50/50 py-1 rounded-r" {...props} />
                          )
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    )}
                  </div>

                  {/* Citation Badges */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-slate-200 flex flex-wrap gap-1.5 items-center">
                      <span className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mr-1 flex items-center">
                        <Bookmark className="w-3 h-3 mr-0.5 text-brand-600" /> Citations:
                      </span>
                      {msg.citations.map((c, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => setTargetPage(c.page)}
                          title={c.snippet ? `Page ${c.page}: ${c.snippet}` : `Jump to Page ${c.page}`}
                          className="px-2 py-0.5 text-[11px] font-medium bg-brand-100 hover:bg-brand-200 text-brand-800 rounded-md transition-colors"
                        >
                          Page {c.page}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-xl bg-slate-800 text-white flex items-center justify-center flex-shrink-0 shadow-sm mt-0.5">
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
              <div className="bg-slate-100 border border-slate-200/60 rounded-2xl rounded-tl-none p-3.5 text-xs text-slate-500 flex items-center space-x-2">
                <Loader2 className="w-4 h-4 animate-spin text-brand-600" />
                <span>Searching ChromaDB & synthesizing response with Gemini...</span>
              </div>
            </div>
          )}

          <div ref={chatBottomRef} />
        </div>

        {/* Input Form */}
        <form onSubmit={handleSend} className="p-3 border-t border-slate-200 bg-white flex space-x-2">
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
            className="flex-1 bg-slate-50 border border-slate-300 rounded-xl px-4 py-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading || !isReady}
            className="px-4 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:bg-slate-200 disabled:text-slate-400 text-white rounded-xl transition-all shadow-sm flex items-center justify-center cursor-pointer disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};

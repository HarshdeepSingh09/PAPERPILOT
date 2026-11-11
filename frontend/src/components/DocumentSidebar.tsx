import React from 'react';
import { FileText, Trash2, Layers, Loader2, AlertCircle } from 'lucide-react';
import { DocumentItem } from '../types';

interface DocumentSidebarProps {
  documents: DocumentItem[];
  selectedDocument: DocumentItem | null;
  onSelectDocument: (doc: DocumentItem) => void;
  onDeleteDocument: (id: string) => void;
}

export const DocumentSidebar: React.FC<DocumentSidebarProps> = ({
  documents,
  selectedDocument,
  onSelectDocument,
  onDeleteDocument,
}) => {
  return (
    <div className="relative flex-1 min-h-0 overflow-y-auto p-3 space-y-1">
      <div className="px-2 py-1 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
        Your Library ({documents.length})
      </div>

      {documents.length === 0 ? (
        <div className="text-center py-10 px-4">
          <FileText className="w-8 h-8 text-slate-300 dark:text-slate-700 mx-auto mb-2" />
          <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">No documents yet</p>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Upload your first PDF, Word doc, or text file to begin.
          </p>
        </div>
      ) : (
        documents.map((doc) => {
          const isSelected = selectedDocument?.id === doc.id;
          const fmt = (doc.file_format || 'pdf').toUpperCase();
          const unit = doc.citation_unit || (fmt === 'PDF' ? 'page' : 'section');
          const cat = doc.document_category || 'General Document';
          const shortCat =
            cat === 'User Manual / Technical Documentation'
              ? 'Tech Manual'
              : cat.replace(' Material', '').replace(' Document', '');
          return (
            <div
              key={doc.id}
              onClick={() => onSelectDocument(doc)}
              className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all ${
                isSelected
                  ? 'bg-brand-50 dark:bg-brand-950/50 border border-brand-200 dark:border-brand-800 text-brand-900 dark:text-brand-100 shadow-sm'
                  : 'hover:bg-slate-100 dark:hover:bg-slate-800/70 border border-transparent text-slate-700 dark:text-slate-200'
              }`}
            >
              <div className="flex items-start space-x-3 overflow-hidden min-w-0">
                <div
                  className={`mt-0.5 p-2 rounded-lg flex-shrink-0 ${
                    isSelected
                      ? 'bg-brand-600 text-white'
                      : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300 group-hover:bg-white dark:group-hover:bg-slate-700'
                  }`}
                >
                  <FileText className="w-4 h-4" />
                </div>
                <div className="overflow-hidden min-w-0">
                  <h4 className="text-xs font-semibold truncate leading-tight" title={doc.original_filename}>
                    {doc.original_filename}
                  </h4>
                  <div className="flex items-center flex-wrap gap-1 mt-1">
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-200/80 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                      {fmt}
                    </span>
                    {doc.status === 'ready' && (
                      <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200/80 dark:border-indigo-800/60 truncate max-w-[115px]">
                        {shortCat}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center space-x-2 mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                    {doc.status === 'ready' ? (
                      <>
                        <span className="flex items-center space-x-0.5">
                          <Layers className="w-3 h-3" />
                          <span>
                            {doc.total_pages}{' '}
                            {unit === 'section'
                              ? doc.total_pages === 1
                                ? 'section'
                                : 'sections'
                              : doc.total_pages === 1
                              ? 'page'
                              : 'pages'}
                          </span>
                        </span>
                        {doc.total_chunks !== undefined && doc.total_chunks > 0 && (
                          <>
                            <span>•</span>
                            <span>{doc.total_chunks} chunks</span>
                          </>
                        )}
                      </>
                    ) : doc.status === 'ocr_required' ? (
                      <span className="text-[10px] font-semibold text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/50 px-1.5 py-0.5 rounded border border-amber-200 dark:border-amber-800/60">
                        OCR Required
                      </span>
                    ) : doc.status === 'failed' ? (
                      <span className="inline-flex items-center space-x-1 text-[10px] font-semibold text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/50 px-1.5 py-0.5 rounded border border-red-200 dark:border-red-800/60">
                        <AlertCircle className="w-2.5 h-2.5" />
                        <span>Failed</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1 text-[10px] font-semibold text-brand-700 dark:text-brand-300 bg-brand-50 dark:bg-brand-950/50 px-1.5 py-0.5 rounded border border-brand-200 dark:border-brand-800/60">
                        <Loader2 className="w-2.5 h-2.5 animate-spin" />
                        <span className="capitalize">{doc.status}...</span>
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteDocument(doc.id);
                }}
                title="Delete document"
                className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 dark:text-slate-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-white dark:hover:bg-slate-800 rounded-lg transition-all"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })
      )}
    </div>
  );
};

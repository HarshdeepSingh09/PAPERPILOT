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
    <div className="flex-1 overflow-y-auto p-3 space-y-1">
      <div className="px-2 py-1 text-xs font-semibold text-slate-400 uppercase tracking-wider">
        Your Library ({documents.length})
      </div>

      {documents.length === 0 ? (
        <div className="text-center py-10 px-4">
          <FileText className="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <p className="text-xs text-slate-500 font-medium">No documents yet</p>
          <p className="text-[11px] text-slate-400 mt-1">
            Upload your first research paper or study PDF to begin.
          </p>
        </div>
      ) : (
        documents.map((doc) => {
          const isSelected = selectedDocument?.id === doc.id;
          return (
            <div
              key={doc.id}
              onClick={() => onSelectDocument(doc)}
              className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all ${
                isSelected
                  ? 'bg-brand-50 border border-brand-200 text-brand-900 shadow-sm'
                  : 'hover:bg-slate-100 border border-transparent text-slate-700'
              }`}
            >
              <div className="flex items-start space-x-3 overflow-hidden">
                <div
                  className={`mt-0.5 p-2 rounded-lg flex-shrink-0 ${
                    isSelected ? 'bg-brand-600 text-white' : 'bg-slate-200 text-slate-600 group-hover:bg-white'
                  }`}
                >
                  <FileText className="w-4 h-4" />
                </div>
                <div className="overflow-hidden">
                  <h4 className="text-xs font-semibold truncate leading-tight">
                    {doc.original_filename}
                  </h4>
                  <div className="flex items-center space-x-2 mt-1 text-[11px] text-slate-400">
                    {doc.status === 'ready' ? (
                      <>
                        <span className="flex items-center space-x-0.5">
                          <Layers className="w-3 h-3" />
                          <span>{doc.total_pages} {doc.total_pages === 1 ? 'page' : 'pages'}</span>
                        </span>
                        {doc.total_chunks !== undefined && doc.total_chunks > 0 && (
                          <>
                            <span>•</span>
                            <span>{doc.total_chunks} chunks</span>
                          </>
                        )}
                      </>
                    ) : doc.status === 'ocr_required' ? (
                      <span className="text-[10px] font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                        OCR Required
                      </span>
                    ) : doc.status === 'failed' ? (
                      <span className="inline-flex items-center space-x-1 text-[10px] font-semibold text-red-700 bg-red-50 px-1.5 py-0.5 rounded border border-red-200">
                        <AlertCircle className="w-2.5 h-2.5" />
                        <span>Failed</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1 text-[10px] font-semibold text-brand-700 bg-brand-50 px-1.5 py-0.5 rounded border border-brand-200">
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
                className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-red-600 hover:bg-white rounded-lg transition-all"
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

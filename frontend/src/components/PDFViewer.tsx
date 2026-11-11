import React, { useState, useEffect, useRef } from 'react';
import {
  FileText,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  RotateCw,
  AlertCircle,
  Loader2,
  ZoomIn,
  ZoomOut,
  AlignLeft,
} from 'lucide-react';
import { DocumentItem, DocumentContentResponse } from '../types';
import { documentApi } from '../api/client';

interface PDFViewerProps {
  document: DocumentItem;
  targetPage?: number | null;
}

export const PDFViewer: React.FC<PDFViewerProps> = ({ document, targetPage }) => {
  const fileFormat = (document.file_format || 'pdf').toLowerCase();
  const isPdf = fileFormat === 'pdf';

  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [textContent, setTextContent] = useState<DocumentContentResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageInput, setPageInput] = useState<string>('1');
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const activeBlobUrlRef = useRef<string | null>(null);
  const sectionReaderRef = useRef<HTMLDivElement>(null);

  // Sync targetPage (page or section index) from external prop (e.g. clicked citations)
  useEffect(() => {
    if (targetPage && targetPage >= 1 && targetPage <= Math.max(document.total_pages, 1)) {
      setCurrentPage(targetPage);
      setPageInput(targetPage.toString());

      if (!isPdf && sectionReaderRef.current) {
        const secEl = window.document.getElementById(`doc-section-${targetPage}`);
        if (secEl) {
          const containerTop = sectionReaderRef.current.getBoundingClientRect().top;
          const elTop = secEl.getBoundingClientRect().top;
          const nextTop = sectionReaderRef.current.scrollTop + (elTop - containerTop) - 12;
          sectionReaderRef.current.scrollTo({ top: Math.max(0, nextTop), behavior: 'smooth' });
        }
      }
    }
  }, [targetPage, document.total_pages, isPdf]);

  const loadDocument = async () => {
    try {
      setIsLoading(true);
      setError(null);
      setTextContent(null);

      if (activeBlobUrlRef.current) {
        URL.revokeObjectURL(activeBlobUrlRef.current);
        activeBlobUrlRef.current = null;
      }

      if (isPdf) {
        const blob = await documentApi.getFileBlob(document.id);
        const url = URL.createObjectURL(blob);
        activeBlobUrlRef.current = url;
        setBlobUrl(url);
      } else {
        setBlobUrl(null);
        const contentData = await documentApi.getContent(document.id);
        setTextContent(contentData);
      }

      const initialPage = targetPage && targetPage <= document.total_pages ? targetPage : 1;
      setCurrentPage(initialPage);
      setPageInput(initialPage.toString());
    } catch (err: any) {
      console.error('Failed to load document preview:', err);
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'Could not fetch document from server. Please verify backend is running.';
      setError(`Failed to retrieve document: ${detail}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDocument();

    return () => {
      if (activeBlobUrlRef.current) {
        URL.revokeObjectURL(activeBlobUrlRef.current);
        activeBlobUrlRef.current = null;
      }
    };
  }, [document.id, fileFormat]);

  const totalUnits = isPdf ? document.total_pages : textContent?.total_sections || document.total_pages || 1;

  const jumpToUnit = (unit: number) => {
    if (unit < 1 || unit > totalUnits) return;
    setCurrentPage(unit);
    setPageInput(unit.toString());
    if (!isPdf && sectionReaderRef.current) {
      const secEl = window.document.getElementById(`doc-section-${unit}`);
      if (secEl) {
        const containerTop = sectionReaderRef.current.getBoundingClientRect().top;
        const elTop = secEl.getBoundingClientRect().top;
        const nextTop = sectionReaderRef.current.scrollTop + (elTop - containerTop) - 12;
        sectionReaderRef.current.scrollTo({ top: Math.max(0, nextTop), behavior: 'smooth' });
      }
    }
  };

  const handlePrevPage = () => jumpToUnit(currentPage - 1);
  const handleNextPage = () => jumpToUnit(currentPage + 1);

  const handlePageInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPageInput(e.target.value);
  };

  const handlePageInputSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = parseInt(pageInput, 10);
    if (!isNaN(parsed) && parsed >= 1 && parsed <= totalUnits) {
      jumpToUnit(parsed);
    } else {
      setPageInput(currentPage.toString());
    }
  };

  const handleZoomIn = () => setZoomLevel((prev) => Math.min(prev + 25, 200));
  const handleZoomOut = () => setZoomLevel((prev) => Math.max(prev - 25, 50));

  const openInNewTab = () => {
    const directUrl = documentApi.getFileUrl(document.id);
    window.open(directUrl, '_blank');
  };

  const pdfViewSrc = blobUrl
    ? `${blobUrl}#page=${currentPage}&zoom=${zoomLevel}&toolbar=1&navpanes=0`
    : '';

  const unitSingular = isPdf ? 'Page' : 'Section';
  const unitPlural = isPdf ? 'pages' : 'sections';
  const sizeFormatted =
    document.file_size_bytes >= 1024 * 1024
      ? `${(document.file_size_bytes / (1024 * 1024)).toFixed(2)} MB`
      : `${Math.max(1, Math.round(document.file_size_bytes / 1024))} KB`;

  return (
    <div className="w-full md:w-1/2 border-b md:border-b-0 md:border-r border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-900/70 flex flex-col h-1/2 md:h-full min-h-0 overflow-hidden relative">
      {/* Top Document Header & Navigation Toolbar */}
      <div className="flex-shrink-0 p-3 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between shadow-xs z-10">
        {/* Left: Document Info */}
        <div className="flex items-center space-x-2 overflow-hidden mr-2">
          <div className="p-1.5 rounded-lg bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 flex-shrink-0">
            {isPdf ? <FileText className="w-4 h-4" /> : <AlignLeft className="w-4 h-4" />}
          </div>
          <div className="overflow-hidden">
            <div className="flex items-center space-x-1.5">
              <h3
                className="text-xs font-semibold text-slate-800 dark:text-slate-100 truncate"
                title={document.original_filename}
              >
                {document.original_filename}
              </h3>
              <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 flex-shrink-0">
                {fileFormat}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 dark:text-slate-500">
              {totalUnits} {totalUnits === 1 ? unitSingular.toLowerCase() : unitPlural} • {sizeFormatted}
            </p>
          </div>
        </div>

        {/* Right: Controls & Page/Section Jump */}
        <div className="flex items-center space-x-1.5 flex-shrink-0">
          {targetPage && targetPage === currentPage && (
            <span className="hidden sm:inline-flex text-[11px] font-semibold text-brand-700 dark:text-brand-300 bg-brand-50 dark:bg-brand-950/60 px-2 py-0.5 rounded-full border border-brand-200 dark:border-brand-800 mr-1">
              Cited {unitSingular} {targetPage}
            </span>
          )}

          {/* Page / Section Navigator */}
          <div className="flex items-center bg-slate-100 dark:bg-slate-800 rounded-lg p-0.5 border border-slate-200 dark:border-slate-700">
            <button
              onClick={handlePrevPage}
              disabled={currentPage <= 1 || isLoading}
              title={`Previous ${unitSingular}`}
              className="p-1 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-white dark:hover:bg-slate-700 rounded disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>

            <form onSubmit={handlePageInputSubmit} className="flex items-center px-1">
              <input
                type="text"
                value={pageInput}
                onChange={handlePageInputChange}
                onBlur={handlePageInputSubmit}
                disabled={isLoading}
                className="w-8 text-center text-xs font-semibold bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 border border-slate-200 dark:border-slate-700 rounded py-0.5 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <span className="text-[11px] text-slate-500 dark:text-slate-400 mx-1">/ {totalUnits}</span>
            </form>

            <button
              onClick={handleNextPage}
              disabled={currentPage >= totalUnits || isLoading}
              title={`Next ${unitSingular}`}
              className="p-1 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-white dark:hover:bg-slate-700 rounded disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Zoom controls (PDF only) */}
          {isPdf && (
            <div className="hidden lg:flex items-center bg-slate-100 dark:bg-slate-800 rounded-lg p-0.5 border border-slate-200 dark:border-slate-700">
              <button
                onClick={handleZoomOut}
                disabled={zoomLevel <= 50 || isLoading}
                title="Zoom Out"
                className="p-1 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-white dark:hover:bg-slate-700 rounded disabled:opacity-30 transition-all"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="text-[10px] font-semibold text-slate-600 dark:text-slate-300 px-1">
                {zoomLevel}%
              </span>
              <button
                onClick={handleZoomIn}
                disabled={zoomLevel >= 200 || isLoading}
                title="Zoom In"
                className="p-1 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-white dark:hover:bg-slate-700 rounded disabled:opacity-30 transition-all"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Reload button */}
          <button
            onClick={loadDocument}
            disabled={isLoading}
            title="Reload Document"
            className="p-1.5 text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-all"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          {/* Open / download original */}
          <button
            onClick={openInNewTab}
            title={isPdf ? 'Open PDF in new tab' : 'Download / open original file'}
            className="p-1.5 text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950/60 rounded-lg transition-all"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 min-h-0 relative bg-slate-200 dark:bg-slate-950 overflow-hidden flex items-center justify-center">
        {isLoading && (
          <div className="absolute inset-0 bg-slate-50/90 dark:bg-slate-900/90 z-20 flex flex-col items-center justify-center p-6 text-center">
            <div className="w-12 h-12 rounded-2xl bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 flex items-center justify-center mb-3 shadow-sm">
              <Loader2 className="w-6 h-6 animate-spin text-brand-600 dark:text-brand-400" />
            </div>
            <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Retrieving Document</h4>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-xs truncate">
              {document.original_filename}
            </p>
            <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">
              Loading {totalUnits} {unitPlural} from backend...
            </p>
          </div>
        )}

        {error && !isLoading && (
          <div className="p-6 max-w-md bg-white dark:bg-slate-900 rounded-2xl border border-red-200 dark:border-red-900/60 shadow-sm text-center m-4">
            <div className="w-10 h-10 rounded-full bg-red-50 dark:bg-red-950/60 text-red-600 dark:text-red-400 flex items-center justify-center mx-auto mb-3">
              <AlertCircle className="w-5 h-5" />
            </div>
            <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100">Unable to Display Document</h4>
            <p className="text-xs text-red-600 dark:text-red-400 mt-1 leading-relaxed">{error}</p>
            <div className="mt-4 flex items-center justify-center space-x-2">
              <button
                onClick={loadDocument}
                className="px-3 py-1.5 text-xs font-semibold bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-all shadow-xs flex items-center space-x-1"
              >
                <RotateCw className="w-3.5 h-3.5" />
                <span>Retry Loading</span>
              </button>
              <button
                onClick={openInNewTab}
                className="px-3 py-1.5 text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-lg transition-all flex items-center space-x-1"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Open Original</span>
              </button>
            </div>
          </div>
        )}

        {/* PDF Inline Viewer */}
        {isPdf && blobUrl && !isLoading && !error && (
          <object
            key={`${document.id}-${currentPage}-${zoomLevel}`}
            data={pdfViewSrc}
            type="application/pdf"
            className="block w-full h-full border-none"
          >
            <iframe
              src={pdfViewSrc}
              title={document.original_filename}
              className="block w-full h-full border-none"
            >
              <div className="p-6 text-center bg-white dark:bg-slate-900 rounded-xl shadow-sm m-6 border border-slate-200 dark:border-slate-800">
                <FileText className="w-8 h-8 text-slate-400 dark:text-slate-500 mx-auto mb-2" />
                <p className="text-xs text-slate-700 dark:text-slate-200 font-medium">
                  Your browser does not support inline PDF viewing.
                </p>
                <a
                  href={blobUrl}
                  download={document.original_filename}
                  className="mt-3 inline-block px-3 py-1.5 bg-brand-600 text-white text-xs font-semibold rounded-lg hover:bg-brand-700"
                >
                  Download PDF
                </a>
              </div>
            </iframe>
          </object>
        )}

        {/* DOCX / TXT Structured Section Reader */}
        {!isPdf && textContent && !isLoading && !error && (
          <div
            ref={sectionReaderRef}
            className="relative w-full h-full overflow-y-auto bg-slate-100 dark:bg-slate-950 p-5 space-y-4"
          >
            {textContent.sections.length === 0 ? (
              <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-8 text-center text-xs text-slate-500 dark:text-slate-400">
                No readable sections available for preview.
              </div>
            ) : (
              textContent.sections.map((sec) => {
                const isHighlighted = targetPage === sec.section_index;
                return (
                  <div
                    key={sec.section_index}
                    id={`doc-section-${sec.section_index}`}
                    className={`bg-white dark:bg-slate-900 rounded-2xl border p-5 shadow-xs transition-all ${
                      isHighlighted
                        ? 'border-brand-400 dark:border-brand-500 ring-2 ring-brand-500/20'
                        : 'border-slate-200 dark:border-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 pb-2.5 mb-3 border-b border-slate-100 dark:border-slate-800">
                      <div className="flex items-center space-x-2 min-w-0">
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-brand-50 dark:bg-brand-950/60 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800 flex-shrink-0">
                          Section {sec.section_index}
                        </span>
                        <h4 className="text-xs font-bold text-slate-800 dark:text-slate-100 truncate">
                          {sec.section_title}
                        </h4>
                      </div>
                      {sec.paragraph_start !== undefined && sec.paragraph_start !== null && (
                        <span className="text-[10px] text-slate-400 dark:text-slate-500 flex-shrink-0">
                          Para {sec.paragraph_start}
                          {sec.paragraph_end && sec.paragraph_end !== sec.paragraph_start
                            ? `-${sec.paragraph_end}`
                            : ''}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap font-normal space-y-2">
                      {sec.content}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
};

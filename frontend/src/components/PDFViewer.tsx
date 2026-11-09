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
  ZoomOut
} from 'lucide-react';
import { DocumentItem } from '../types';
import { documentApi } from '../api/client';

interface PDFViewerProps {
  document: DocumentItem;
  targetPage?: number | null;
}

export const PDFViewer: React.FC<PDFViewerProps> = ({ document, targetPage }) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageInput, setPageInput] = useState<string>('1');
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const activeBlobUrlRef = useRef<string | null>(null);

  // Sync targetPage from external prop (e.g. clicked citations)
  useEffect(() => {
    if (targetPage && targetPage >= 1 && targetPage <= document.total_pages) {
      setCurrentPage(targetPage);
      setPageInput(targetPage.toString());
    }
  }, [targetPage, document.total_pages]);

  // Load PDF file as Blob whenever document.id changes
  const loadPdf = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Clean up previous blob URL
      if (activeBlobUrlRef.current) {
        URL.revokeObjectURL(activeBlobUrlRef.current);
        activeBlobUrlRef.current = null;
      }

      const blob = await documentApi.getFileBlob(document.id);
      const url = URL.createObjectURL(blob);
      activeBlobUrlRef.current = url;
      setBlobUrl(url);

      // Reset to page 1 or targetPage
      const initialPage = targetPage && targetPage <= document.total_pages ? targetPage : 1;
      setCurrentPage(initialPage);
      setPageInput(initialPage.toString());
    } catch (err: any) {
      console.error('Failed to load PDF file:', err);
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'Could not fetch PDF from server. Please verify backend is running.';
      setError(`Failed to retrieve document: ${detail}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadPdf();

    return () => {
      if (activeBlobUrlRef.current) {
        URL.revokeObjectURL(activeBlobUrlRef.current);
        activeBlobUrlRef.current = null;
      }
    };
  }, [document.id]);

  const handlePrevPage = () => {
    if (currentPage > 1) {
      const next = currentPage - 1;
      setCurrentPage(next);
      setPageInput(next.toString());
    }
  };

  const handleNextPage = () => {
    if (currentPage < document.total_pages) {
      const next = currentPage + 1;
      setCurrentPage(next);
      setPageInput(next.toString());
    }
  };

  const handlePageInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPageInput(e.target.value);
  };

  const handlePageInputSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = parseInt(pageInput, 10);
    if (!isNaN(parsed) && parsed >= 1 && parsed <= document.total_pages) {
      setCurrentPage(parsed);
    } else {
      setPageInput(currentPage.toString());
    }
  };

  const handleZoomIn = () => {
    setZoomLevel((prev) => Math.min(prev + 25, 200));
  };

  const handleZoomOut = () => {
    setZoomLevel((prev) => Math.max(prev - 25, 50));
  };

  const openInNewTab = () => {
    const directUrl = documentApi.getFileUrl(document.id);
    window.open(directUrl, '_blank');
  };

  // Construct PDF view URL with standard viewer hash params
  const pdfViewSrc = blobUrl
    ? `${blobUrl}#page=${currentPage}&zoom=${zoomLevel}&toolbar=1&navpanes=0`
    : '';

  return (
    <div className="w-1/2 border-r border-slate-200 bg-slate-100 flex flex-col h-full overflow-hidden">
      {/* Top Document Header & Navigation Toolbar */}
      <div className="p-3 bg-white border-b border-slate-200 flex items-center justify-between shadow-xs z-10">
        {/* Left: Document Info */}
        <div className="flex items-center space-x-2 overflow-hidden mr-2">
          <div className="p-1.5 rounded-lg bg-brand-50 text-brand-600 flex-shrink-0">
            <FileText className="w-4 h-4" />
          </div>
          <div className="overflow-hidden">
            <h3 className="text-xs font-semibold text-slate-800 truncate" title={document.original_filename}>
              {document.original_filename}
            </h3>
            <p className="text-[10px] text-slate-400">
              {document.total_pages} {document.total_pages === 1 ? 'page' : 'pages'} • {(document.file_size_bytes / (1024 * 1024)).toFixed(2)} MB
            </p>
          </div>
        </div>

        {/* Right: Controls & Page Jump */}
        <div className="flex items-center space-x-1.5 flex-shrink-0">
          {/* Target citation indicator */}
          {targetPage && targetPage === currentPage && (
            <span className="hidden sm:inline-flex text-[11px] font-semibold text-brand-700 bg-brand-50 px-2 py-0.5 rounded-full border border-brand-200 mr-1">
              Cited Page {targetPage}
            </span>
          )}

          {/* Page Navigator */}
          <div className="flex items-center bg-slate-100 rounded-lg p-0.5 border border-slate-200">
            <button
              onClick={handlePrevPage}
              disabled={currentPage <= 1 || isLoading}
              title="Previous Page"
              className="p-1 text-slate-600 hover:text-slate-900 hover:bg-white rounded disabled:opacity-30 disabled:cursor-not-allowed transition-all"
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
                className="w-8 text-center text-xs font-semibold bg-white border border-slate-200 rounded py-0.5 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <span className="text-[11px] text-slate-500 mx-1">/ {document.total_pages}</span>
            </form>

            <button
              onClick={handleNextPage}
              disabled={currentPage >= document.total_pages || isLoading}
              title="Next Page"
              className="p-1 text-slate-600 hover:text-slate-900 hover:bg-white rounded disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Zoom controls */}
          <div className="hidden md:flex items-center bg-slate-100 rounded-lg p-0.5 border border-slate-200">
            <button
              onClick={handleZoomOut}
              disabled={zoomLevel <= 50 || isLoading}
              title="Zoom Out"
              className="p-1 text-slate-600 hover:text-slate-900 hover:bg-white rounded disabled:opacity-30 transition-all"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[10px] font-semibold text-slate-600 px-1">{zoomLevel}%</span>
            <button
              onClick={handleZoomIn}
              disabled={zoomLevel >= 200 || isLoading}
              title="Zoom In"
              className="p-1 text-slate-600 hover:text-slate-900 hover:bg-white rounded disabled:opacity-30 transition-all"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Reload button */}
          <button
            onClick={loadPdf}
            disabled={isLoading}
            title="Reload PDF"
            className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-all"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          {/* Open full tab */}
          <button
            onClick={openInNewTab}
            title="Open PDF in new tab"
            className="p-1.5 text-slate-500 hover:text-brand-600 hover:bg-brand-50 rounded-lg transition-all"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 relative bg-slate-200 overflow-hidden flex items-center justify-center">
        {isLoading && (
          <div className="absolute inset-0 bg-slate-50/90 z-20 flex flex-col items-center justify-center p-6 text-center">
            <div className="w-12 h-12 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center mb-3 shadow-sm">
              <Loader2 className="w-6 h-6 animate-spin text-brand-600" />
            </div>
            <h4 className="text-sm font-semibold text-slate-800">Retrieving Document</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-xs truncate">
              {document.original_filename}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Streaming {document.total_pages} pages from backend...
            </p>
          </div>
        )}

        {error && !isLoading && (
          <div className="p-6 max-w-md bg-white rounded-2xl border border-red-200 shadow-sm text-center m-4">
            <div className="w-10 h-10 rounded-full bg-red-50 text-red-600 flex items-center justify-center mx-auto mb-3">
              <AlertCircle className="w-5 h-5" />
            </div>
            <h4 className="text-sm font-bold text-slate-800">Unable to Display PDF</h4>
            <p className="text-xs text-red-600 mt-1 leading-relaxed">{error}</p>
            <div className="mt-4 flex items-center justify-center space-x-2">
              <button
                onClick={loadPdf}
                className="px-3 py-1.5 text-xs font-semibold bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-all shadow-xs flex items-center space-x-1"
              >
                <RotateCw className="w-3.5 h-3.5" />
                <span>Retry Loading</span>
              </button>
              <button
                onClick={openInNewTab}
                className="px-3 py-1.5 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-all flex items-center space-x-1"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Open in Tab</span>
              </button>
            </div>
          </div>
        )}

        {blobUrl && !isLoading && !error && (
          <object
            key={`${document.id}-${currentPage}-${zoomLevel}`}
            data={pdfViewSrc}
            type="application/pdf"
            className="w-full h-full border-none"
          >
            {/* Fallback iframe for browsers that don't embed object application/pdf directly */}
            <iframe
              src={pdfViewSrc}
              title={document.original_filename}
              className="w-full h-full border-none"
            >
              <div className="p-6 text-center bg-white rounded-xl shadow-sm m-6">
                <FileText className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                <p className="text-xs text-slate-700 font-medium">
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
      </div>
    </div>
  );
};

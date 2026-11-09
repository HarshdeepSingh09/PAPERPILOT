import React, { useState, useRef } from 'react';
import { UploadCloud, Loader2, AlertCircle } from 'lucide-react';
import { documentApi } from '../api/client';
import { DocumentItem } from '../types';

interface DocumentUploadProps {
  onUploadSuccess: (newDoc: DocumentItem) => void;
}

export const DocumentUpload: React.FC<DocumentUploadProps> = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please upload a valid PDF document.');
      return;
    }

    try {
      setIsUploading(true);
      setError(null);
      const doc = await documentApi.upload(file);
      onUploadSuccess(doc);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to upload document. Please check backend server.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="p-4 border-b border-slate-200 bg-white">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all ${
          isDragging
            ? 'border-brand-500 bg-brand-50/50'
            : 'border-slate-300 hover:border-brand-400 hover:bg-slate-50'
        }`}
      >
        <input
          type="file"
          ref={fileInputRef}
          accept=".pdf"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files[0]) {
              handleFile(e.target.files[0]);
            }
          }}
        />

        <div className="flex flex-col items-center justify-center space-y-2">
          {isUploading ? (
            <>
              <Loader2 className="w-8 h-8 text-brand-600 animate-spin" />
              <p className="text-sm font-medium text-slate-700">Extracting & indexing document...</p>
            </>
          ) : (
            <>
              <div className="w-10 h-10 rounded-full bg-brand-50 text-brand-600 flex items-center justify-center">
                <UploadCloud className="w-5 h-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800">
                  Click or drag PDF here
                </p>
                <p className="text-xs text-slate-500">FastAPI + PyMuPDF pipeline</p>
              </div>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-3 p-2.5 bg-red-50 border border-red-200 rounded-lg flex items-center space-x-2 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
};

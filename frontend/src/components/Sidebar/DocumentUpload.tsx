import React, { useState, useRef } from 'react';
import { UploadCloud } from 'lucide-react';

interface DocumentUploadProps {
  onUpload: (files: File[]) => Promise<void>;
  isUploading: boolean;
  uploadProgress: number;
}

export const DocumentUpload: React.FC<DocumentUploadProps> = ({ onUpload, isUploading, uploadProgress }) => {
  const [isDragover, setIsDragover] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragover(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragover(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragover(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files).filter(f => f.type === 'application/pdf');
      if (files.length > 0) {
        onUpload(files);
      } else {
        alert('Please upload PDF files only.');
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files).filter(f => f.type === 'application/pdf');
      if (files.length > 0) {
        onUpload(files);
      }
    }
  };

  return (
    <div 
      className={`upload-section ${isDragover ? 'dragover' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input 
        type="file" 
        accept="application/pdf" 
        multiple
        ref={fileInputRef} 
        onChange={handleFileChange}
        disabled={isUploading}
      />
      <div style={{ pointerEvents: 'none' }}>
        <UploadCloud size={32} style={{ color: 'var(--accent-violet)', marginBottom: '0.75rem', display: 'block', margin: '0 auto' }} />
        <p style={{ fontWeight: 500, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
          Upload Legal Document
        </p>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Drag & drop or click to select (PDF)
        </p>
      </div>

      {isUploading && (
        <div style={{ marginTop: '1rem' }}>
          <div className="progress-bar">
            <div className="progress-bar__fill" style={{ width: `${uploadProgress}%` }} />
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', marginTop: '0.5rem' }}>
            {uploadProgress === 100 ? 'Finalizing...' : `Uploading... ${uploadProgress}%`}
          </p>
        </div>
      )}
    </div>
  );
};

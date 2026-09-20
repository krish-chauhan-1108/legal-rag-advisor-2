import React, { useState, useEffect } from 'react';
import { Database, UploadCloud, File, Trash2, Loader2, CheckCircle2 } from 'lucide-react';

const CONFIGURED_API_URL = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000';
// Production uses Vercel's same-origin proxy so browser extensions cannot block the Render hostname.
const API_URL = import.meta.env.PROD ? '' : CONFIGURED_API_URL;

interface DocumentInfo {
  document_name: string;
  chunk_count: number;
}

export const KnowledgeBaseView: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = () => {
    fetch(`${API_URL}/api/documents`)
    .then(r => r.ok ? r.json() : { documents: [] })
    .then(data => setDocuments(data.documents || []))
    .catch(e => console.error(e));
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    
    setIsUploading(true);
    setError(null);
    
    try {
      const res = await fetch(`${API_URL}/api/ingest`, {
        method: 'POST',
        body: formData
      });
      
      if (res.ok) {
        fetchDocuments();
      } else {
        const data = await res.json();
        setError(data.detail || "Upload failed");
      }
    } catch {
      setError("Network error during upload");
    } finally {
      setIsUploading(false);
      e.target.value = ''; // reset input
    }
  };

  const handleDelete = async (docName: string) => {
    if (!confirm(`Are you sure you want to delete ${docName} from your Knowledge Base?`)) return;
    
    try {
      const res = await fetch(`${API_URL}/api/documents?document_name=${encodeURIComponent(docName)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchDocuments();
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white overflow-y-auto">
      <header className="h-16 border-b border-gray-100 flex items-center px-8 flex-shrink-0 bg-white">
        <h2 className="text-xl font-serif tracking-tight text-[#121212]">Your Knowledge Base</h2>
      </header>

      <div className="p-8 max-w-4xl mx-auto w-full space-y-8">
        
        {/* Upload Section */}
        <div className="bg-[#F9F9F8] border border-gray-200 rounded-xl p-8 text-center">
          <UploadCloud className="w-12 h-12 text-[#1E293B] mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">Upload Legal Documents</h3>
          <p className="text-sm text-gray-500 mb-6">
            PDF documents uploaded here will be permanently stored and accessible across all your chats.
          </p>
          
          {error && <div className="mb-4 text-red-500 text-sm">{error}</div>}
          
          <label className="relative inline-flex items-center gap-2 bg-[#1E293B] text-white px-6 py-3 rounded-lg hover:bg-[#0F172A] cursor-pointer transition-colors font-medium text-sm overflow-hidden">
            {isUploading ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Ingesting Document...</>
            ) : (
              <>Select PDF File</>
            )}
            <input 
              type="file" 
              accept=".pdf" 
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              onChange={handleFileUpload}
              disabled={isUploading}
            />
          </label>
        </div>

        {/* Document List */}
        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center gap-2">
            <Database className="w-5 h-5 text-gray-400" />
            Indexed Documents ({documents.length})
          </h3>
          
          {documents.length === 0 ? (
            <div className="text-center py-12 text-gray-400 border border-dashed border-gray-200 rounded-xl">
              <p className="text-sm">No documents in your knowledge base yet.</p>
            </div>
          ) : (
            <div className="border border-gray-200 rounded-xl divide-y divide-gray-100 bg-white">
              {documents.map((doc, idx) => (
                <div key={idx} className="flex items-center justify-between p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-[#F9F9F8] border border-gray-200 flex items-center justify-center">
                      <File className="w-5 h-5 text-gray-500" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{doc.document_name}</p>
                      <p className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                        <CheckCircle2 className="w-3 h-3 text-green-500" />
                        {doc.chunk_count} chunks indexed
                      </p>
                    </div>
                  </div>
                  <button 
                    onClick={() => handleDelete(doc.document_name)}
                    className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

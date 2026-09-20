export interface SourceChunk {
  content: string;
  document_name: string;
  section: string;
  relevance_score: number;
  page_number?: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceChunk[];
  model_used?: string;
  processing_time_seconds?: number;
}

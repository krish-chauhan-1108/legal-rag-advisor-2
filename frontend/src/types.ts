export interface SourceChunk {
  content: string;
  document_name: string;
  section: string;
  relevance_score: number;
  page_number?: number;
}

export interface ApplicableLaw {
  code: string;
  section: string;
  quote: string;
  explanation: string;
}

export interface StructuredAnalysis {
  is_conversational?: boolean;
  conversational_reply?: string | null;
  suggest_lawyer?: boolean;
  general_analysis?: string;
  situation_meaning?: string;
  bail_status?: string;
  next_24_hours?: string[];
  rights?: string[];
  handling_authority?: string;
  applicable_laws?: ApplicableLaw[];
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceChunk[];
  model_used?: string;
  processing_time_seconds?: number;
}

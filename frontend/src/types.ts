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
  created_at?: string;
}

export interface PersistedChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  structured_content?: StructuredAnalysis | null;
  sources?: SourceChunk[] | null;
  model_used?: string | null;
  processing_time_seconds?: number | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  user_email: string;
  messages: PersistedChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface AuthUser {
  id: string;
  google_id: string;
  email: string;
  name?: string | null;
  picture?: string | null;
}

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
  is_conversational: boolean;
  conversational_reply: string | null;
  summary: string;
  applicable_laws: ApplicableLaw[];
  immediate_actions: string[];
  bail_info: string;
  detailed_analysis: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string; // Keep this as fallback or for user messages
  structuredContent?: StructuredAnalysis; // For JSON responses
  sources?: SourceChunk[];
  model_used?: string;
  processing_time_seconds?: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  isGenerating: boolean;
  createdAt: number;
  updatedAt: number;
}

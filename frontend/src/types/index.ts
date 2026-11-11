export type DocumentStatus =
  | 'ready'
  | 'uploaded'
  | 'extracting'
  | 'embedding'
  | 'indexing'
  | 'processing'
  | 'ocr_required'
  | 'failed';

export type DocumentCategory =
  | 'Educational Material'
  | 'Research Paper'
  | 'Business Report'
  | 'Meeting Notes'
  | 'Legal Document'
  | 'Financial Report'
  | 'User Manual / Technical Documentation'
  | 'General Document';

export const DOCUMENT_CATEGORIES: DocumentCategory[] = [
  'Educational Material',
  'Research Paper',
  'Business Report',
  'Meeting Notes',
  'Legal Document',
  'Financial Report',
  'User Manual / Technical Documentation',
  'General Document',
];

export interface DocumentItem {
  id: string;
  original_filename: string;
  filename: string;
  file_size_bytes: number;
  total_pages: number;
  extracted_pages?: number;
  total_characters?: number;
  total_chunks?: number;
  status: DocumentStatus;
  embedding_status?: string;
  embedding_model?: string;
  title?: string;
  chapter_name?: string;
  chapter_number?: string;
  subject?: string;
  file_format?: string;
  document_category?: DocumentCategory;
  classification_confidence?: number;
  classification_source?: string;
  classification_reason?: string;
  citation_unit?: 'page' | 'section';
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentContentSection {
  section_index: number;
  section_title: string;
  paragraph_start?: number;
  paragraph_end?: number;
  content: string;
  char_count: number;
}

export interface DocumentContentResponse {
  document_id: string;
  original_filename: string;
  file_format: string;
  citation_unit: 'page' | 'section';
  total_sections: number;
  headings: Array<{ level: number; text: string; paragraph_index: number }>;
  sections: DocumentContentSection[];
}

export interface AdaptiveInsightsResponse {
  id?: string;
  document_id: string;
  category: DocumentCategory;
  title: string;
  generation_source: 'gemini' | 'extractive' | string;
  insights: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface DocumentChunkItem {
  id: string;
  chunk_index: number;
  char_count: number;
  page_start: number;
  page_end: number;
  pages: number[];
  content: string;
  created_at?: string;
}

export interface DocumentStats {
  document_id: string;
  original_filename: string;
  total_pages: number;
  extracted_pages: number;
  total_characters: number;
  total_chunks: number;
  status: string;
  error_message?: string;
  average_chunk_size: number;
}

export interface Citation {
  page: number;
  snippet?: string;
  chunk_index?: number;
  label?: string;
  source_type?: 'page' | 'section';
  section_title?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  created_at: string;
}

export interface MCQOption {
  id: string;
  text: string;
}

export interface QuizQuestion {
  id: number;
  question: string;
  options: MCQOption[];
  question_type: string;
  correct_option_id?: string;
  correct_options?: string[];
  explanation?: string;
  source_page?: number;
  user_answer?: string | string[];
}

export type MCQQuestion = QuizQuestion;

export interface QuizData {
  id: string;
  document_id: string;
  title: string;
  difficulty: string;
  question_count: number;
  total_questions: number;
  completed: boolean;
  score?: number;
  percentage?: number;
  questions: QuizQuestion[];
  created_at?: string;
  completed_at?: string;
}

export interface ConceptItem {
  term: string;
  definition: string;
  source_page?: number;
}

export interface FormulaEquationItem {
  name: string;
  equation_latex: string;
  explanation: string;
  source_page?: number;
}

export interface ChapterSummaryItem {
  chapter_title: string;
  summary: string;
  key_points: string[];
  source_page?: number;
}

export interface FactItem {
  fact: string;
  category?: string;
  source_page?: number;
}

export interface PageRefItem {
  page: number;
  topic: string;
  snippet?: string;
}

export interface DocumentSummary {
  id?: string;
  document_id: string;
  title: string;
  overview: string;
  executive_overview: string;
  key_takeaways: string[];
  important_concepts?: ConceptItem[];
  formulas_equations?: FormulaEquationItem[];
  chapter_summaries?: ChapterSummaryItem[];
  important_facts?: FactItem[];
  page_references?: PageRefItem[];
  important_sections?: Array<{
    section: string;
    page: number;
    summary: string;
  }>;
}

export interface DefinitionItem {
  term: string;
  definition: string;
  source_page?: number;
}

export interface KeyConceptItem {
  concept: string;
  summary: string;
  key_points: string[];
  source_page?: number;
}

export interface ReactionEquationItem {
  reaction_type: string;
  equation_latex: string;
  description: string;
  source_page?: number;
}

export interface RevisionFormulaItem {
  formula_name: string;
  formula_latex: string;
  usage: string;
  source_page?: number;
}

export interface ComparisonParameter {
  parameter: string;
  item_a: string;
  item_b: string;
}

export interface DifferenceComparisonItem {
  topic: string;
  aspect_a: string;
  aspect_b: string;
  comparison_points: ComparisonParameter[];
  source_page?: number;
}

export interface FAQItem {
  question: string;
  answer: string;
  source_page?: number;
}

export interface LastMinutePoint {
  point: string;
  source_page?: number;
}

export interface RevisionNotesData {
  id?: string;
  document_id: string;
  title: string;
  chapter_overview: string;
  definitions: DefinitionItem[];
  key_concepts: KeyConceptItem[];
  reactions_equations: ReactionEquationItem[];
  formulas: RevisionFormulaItem[];
  differences_comparisons: DifferenceComparisonItem[];
  faqs: FAQItem[];
  last_minute_points: LastMinutePoint[];
}

export type RevisionConcept = KeyConceptItem;

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthSessionResponse {
  authenticated: boolean;
  user: UserProfile;
  message: string;
}

export interface ForgotPasswordResponse {
  message: string;
  email_delivery_configured: boolean;
}

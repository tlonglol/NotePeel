// User types
export interface User {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  created_at: string;
}

export interface UserCreate {
  email: string;
  username: string;
  password: string;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

// Note types
export interface Note {
  id: number;
  title: string;
  image_filename: string;
  status: string;
  created_at: string;
  processed_at?: string;
  raw_text?: string;
  structured_text?: string;
  error_message?: string;
  subject?: string;
  topic?: string;
  tags?: string;
}

export interface NoteWithImage extends Note {
  image_url: string;
  image_mimetype: string;
  raw_text: string;
  structured_text: string;
  error_message?: string;
}

// Categories for filtering
export interface Categories {
  subjects: string[];
  topics: string[];
  tags: string[];
}

// Flashcard types
export interface Flashcard {
  id: number;
  question: string;
  answer: string;
}

export interface FlashcardSet {
  id: number;
  note_id: number;
  title: string;
  cards: Flashcard[];
  created_at: string;
}

// Shared note (public view)
export interface SharedNote {
  title: string;
  structured_text: string;
  raw_text: string;
  subject?: string;
  topic?: string;
  tags?: string;
  created_at: string;
  owner_username?: string;
}

// Notebook types
export interface Notebook {
  id: number;
  name: string;
  color: string;
  owner_id: number;
  created_at: string;
  updated_at: string;
  note_count: number;
}

export interface NotebookWithNotes extends Notebook {
  notes: Note[];
}

export interface NotebookCreate {
  name: string;
  color?: string;
}

export interface NotebookUpdate {
  name?: string;
  color?: string;
}

// Ask-your-notes (retrieval-grounded Q&A)
export interface AskCitation {
  n: number;
  chunk_id: number;
  note_id: number;
  note_title: string;
  page: number;
  heading: string | null;
  snippet: string;
}

export interface AskResult {
  question: string;
  answer: string;
  abstained: boolean;
  gate_triggered: boolean;
  citations: AskCitation[];
  sources: AskCitation[];
  retrieval_mode: string;
  top_score: number | null;
  guard_flagged_chunk_ids: number[];
  model: string | null;
  timings_ms: Record<string, number>;
  query_id: number | null;
}

export interface AskConfig {
  retrieval_mode: string;
  generation_model: string;
  streaming: boolean;
}

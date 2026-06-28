import type {
  UserCreate,
  UserLogin,
  AuthToken,
  User,
  Note,
  NoteWithImage,
  SharedNote,
  Notebook,
  NotebookWithNotes,
  NotebookCreate,
  NotebookUpdate,
  Categories,
  FlashcardSet
} from '../types';

// Backend base URL. Configurable per environment via VITE_API_URL
// (set at build time); falls back to the local dev server.
// Strip any trailing slash(es) so `${API_URL}/api/...` never doubles up.
const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');

const getToken = (): string | null => localStorage.getItem('token');

// Handle token expiration - clear storage and redirect to login
const handleTokenExpired = () => {
  localStorage.removeItem('token');
  localStorage.removeItem('userEmail');
  
  // Store a message to show on login page
  sessionStorage.setItem('sessionExpired', 'true');
  
  // Redirect to login (force page reload to reset React state)
  window.location.href = '/';
};

async function fetchWithAuth<T>(url: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = { ...options.headers };
  
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }
  
  if (!(options.body instanceof FormData)) {
    (headers as Record<string, string>)['Content-Type'] = 'application/json';
  }
  
  let response: Response;
  try {
    response = await fetch(`${API_URL}${url}`, { ...options, headers });
  } catch (networkError) {
    // Network error - server unreachable
    console.error('Network error:', networkError);
    throw new Error('Cannot connect to server. Is the backend running on port 8000?');
  }
  
  // Handle 401 Unauthorized (token expired or invalid)
  if (response.status === 401) {
    // Don't redirect on login/register attempts
    if (!url.includes('/auth/login') && !url.includes('/auth/register')) {
      handleTokenExpired();
      throw new Error('Session expired. Please log in again.');
    }
  }
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }
  
  // Handle 204 No Content (e.g., DELETE requests)
  if (response.status === 204) {
    return undefined as T;
  }
  
  return response.json();
}

export const authAPI = {
  register: (data: UserCreate): Promise<User> => 
    fetchWithAuth('/api/auth/register', { method: 'POST', body: JSON.stringify(data) }),
    
  login: (data: UserLogin): Promise<AuthToken> =>
    fetchWithAuth('/api/auth/login', { method: 'POST', body: JSON.stringify(data) }),
    
  getMe: (): Promise<User> => fetchWithAuth('/api/auth/me'),

  googleLogin: (credential: string): Promise<AuthToken> =>
    fetchWithAuth('/api/auth/google', { method: 'POST', body: JSON.stringify({ credential }) }),
};

// Request presigned URLs, then PUT each file directly to S3.
// Keeps large uploads off the Lambda Function URL (6MB request limit).
async function presignAndPut(files: File[]): Promise<string[]> {
  const { uploads } = await fetchWithAuth<{ uploads: Array<{ key: string; url: string }> }>(
    '/api/notes/upload-url',
    {
      method: 'POST',
      body: JSON.stringify({
        files: files.map(f => ({ filename: f.name, content_type: f.type || 'image/jpeg' })),
      }),
    }
  );

  await Promise.all(
    uploads.map((u, i) =>
      fetch(u.url, {
        method: 'PUT',
        headers: { 'Content-Type': files[i].type || 'image/jpeg' },
        body: files[i],
      }).then(r => {
        if (!r.ok) throw new Error('Upload to storage failed');
      })
    )
  );

  return uploads.map(u => u.key);
}

export const notesAPI = {
  upload: async (file: File, noteType: string = 'default'): Promise<Note> => {
    const [key] = await presignAndPut([file]);
    return fetchWithAuth(`/api/notes/process?note_type=${noteType}`, {
      method: 'POST',
      body: JSON.stringify({ keys: [key], filenames: [file.name] }),
    });
  },

  uploadMultiPage: async (files: File[], noteType: string = 'default', title?: string): Promise<Note> => {
    const keys = await presignAndPut(files);
    return fetchWithAuth(`/api/notes/process?note_type=${noteType}`, {
      method: 'POST',
      body: JSON.stringify({ keys, filenames: files.map(f => f.name), title }),
    });
  },

  getAll: (): Promise<Note[]> => fetchWithAuth('/api/notes/'),

  search: (query: string, subject?: string, topic?: string): Promise<Note[]> => {
    const params = new URLSearchParams();
    if (query) params.set('q', query);
    if (subject) params.set('subject', subject);
    if (topic) params.set('topic', topic);
    return fetchWithAuth(`/api/notes/search?${params.toString()}`);
  },

  getCategories: (): Promise<Categories> => fetchWithAuth('/api/notes/categories'),
    
  getById: (id: number): Promise<NoteWithImage> => fetchWithAuth(`/api/notes/${id}/full`),
    
  update: (id: number, data: { structured_text?: string; title?: string; subject?: string; topic?: string; tags?: string }): Promise<{ message: string }> =>
    fetchWithAuth(`/api/notes/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  delete: (id: number): Promise<{ message: string }> =>
    fetchWithAuth(`/api/notes/${id}`, { method: 'DELETE' }),

  reprocess: (id: number): Promise<{ raw_text: string; structured_text: string; pass: number | null }> =>
    fetchWithAuth(`/api/notes/${id}/reprocess`, { method: 'POST' }),

  share: (id: number): Promise<{ share_token: string }> =>
    fetchWithAuth(`/api/notes/${id}/share`, { method: 'POST' }),

  unshare: (id: number): Promise<{ message: string }> =>
    fetchWithAuth(`/api/notes/${id}/share`, { method: 'DELETE' }),

  getShared: (token: string): Promise<SharedNote> =>
    fetch(`${API_URL}/api/notes/shared/${token}`).then(r => {
      if (!r.ok) throw new Error('Shared note not found');
      return r.json();
    }),

  // AI Features
  generateFlashcards: (noteId: number, regenerate: boolean = false): Promise<FlashcardSet & { cached?: boolean }> =>
    fetchWithAuth(`/api/ai/flashcards/${noteId}?regenerate=${regenerate}`, { method: 'POST' }),

  getFlashcards: (noteId: number): Promise<FlashcardSet[]> =>
    fetchWithAuth(`/api/ai/flashcards/${noteId}`),

  summarize: (noteId: number, regenerate: boolean = false): Promise<{ summary: string; cached?: boolean }> =>
    fetchWithAuth(`/api/ai/summarize/${noteId}?regenerate=${regenerate}`, { method: 'POST' }),

  explain: (text: string, noteId?: number): Promise<{ explanation: string; highlighted_text: string; cached?: boolean }> =>
    fetchWithAuth('/api/ai/explain', { method: 'POST', body: JSON.stringify({ text, note_id: noteId }) }),

  getExplanations: (noteId: number): Promise<{ id: number; highlighted_text: string; explanation: string; created_at: string }[]> =>
    fetchWithAuth(`/api/ai/explanations/${noteId}`),
};

export const notebooksAPI = {
  create: (data: NotebookCreate): Promise<Notebook> =>
    fetchWithAuth('/api/notebooks/', { method: 'POST', body: JSON.stringify(data) }),

  getAll: (): Promise<Notebook[]> => 
    fetchWithAuth('/api/notebooks/'),

  getById: (id: number): Promise<NotebookWithNotes> => 
    fetchWithAuth(`/api/notebooks/${id}`),

  update: (id: number, data: NotebookUpdate): Promise<Notebook> =>
    fetchWithAuth(`/api/notebooks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  delete: (id: number): Promise<void> =>
    fetchWithAuth(`/api/notebooks/${id}`, { method: 'DELETE' }),

  addNote: (notebookId: number, noteId: number): Promise<{ message: string }> =>
    fetchWithAuth(`/api/notebooks/${notebookId}/notes`, { 
      method: 'POST', 
      body: JSON.stringify({ note_id: noteId }) 
    }),

  removeNote: (notebookId: number, noteId: number): Promise<{ message: string }> =>
    fetchWithAuth(`/api/notebooks/${notebookId}/notes/${noteId}`, { method: 'DELETE' }),

  getAvailableNotes: (notebookId: number): Promise<Note[]> =>
    fetchWithAuth(`/api/notebooks/${notebookId}/available-notes`),
};

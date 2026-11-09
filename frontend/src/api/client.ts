import axios from 'axios';
import {
  DocumentItem,
  ChatMessage,
  DocumentSummary,
  QuizData,
  RevisionNotesData,
} from '../types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const documentApi = {
  list: async (): Promise<DocumentItem[]> => {
    const res = await api.get('/documents');
    return res.data;
  },

  get: async (id: string): Promise<DocumentItem> => {
    const res = await api.get(`/documents/${id}`);
    return res.data;
  },

  upload: async (file: File): Promise<DocumentItem> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await api.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/documents/${id}`);
  },

  reprocess: async (id: string): Promise<DocumentItem> => {
    const res = await api.post(`/documents/${id}/reprocess`);
    return res.data;
  },

  getFileUrl: (id: string): string => {
    const base = import.meta.env.VITE_API_BASE_URL || '/api/v1';
    return `${base}/documents/${id}/file`;
  },

  getFileBlob: async (id: string): Promise<Blob> => {
    const res = await api.get(`/documents/${id}/file`, {
      responseType: 'blob',
    });
    return res.data;
  },

  getStats: async (id: string) => {
    const res = await api.get(`/documents/${id}/stats`);
    return res.data;
  },

  getChunks: async (id: string, skip = 0, limit = 100) => {
    const res = await api.get(`/documents/${id}/chunks`, {
      params: { skip, limit },
    });
    return res.data;
  },
};

export const chatApi = {
  sendMessage: async (documentId: string, message: string, topK = 4): Promise<ChatMessage> => {
    const res = await api.post(`/documents/${documentId}/chat`, { message, top_k: topK });
    return res.data;
  },

  getHistory: async (documentId: string): Promise<ChatMessage[]> => {
    const res = await api.get(`/documents/${documentId}/chat/history`);
    return res.data;
  },

  clearHistory: async (documentId: string): Promise<{ document_id: string; deleted_count: number; message: string }> => {
    const res = await api.delete(`/documents/${documentId}/chat/history`);
    return res.data;
  },
};

export const studyApi = {
  getSummary: async (documentId: string): Promise<DocumentSummary> => {
    const res = await api.get(`/summaries/${documentId}`);
    return res.data;
  },

  generateSummary: async (
    documentId: string,
    format = 'comprehensive',
    forceRegenerate = false
  ): Promise<DocumentSummary> => {
    const res = await api.post('/summaries/generate', {
      document_id: documentId,
      format,
      force_regenerate: forceRegenerate,
    });
    return res.data;
  },

  getLatestQuiz: async (documentId: string): Promise<QuizData> => {
    const res = await api.get(`/quizzes/document/${documentId}`);
    return res.data;
  },

  getQuiz: async (quizId: string): Promise<QuizData> => {
    const res = await api.get(`/quizzes/${quizId}`);
    return res.data;
  },

  generateQuiz: async (
    documentId: string,
    numQuestions = 5,
    difficulty = 'medium',
    questionType = 'mixed',
    forceRegenerate = false
  ): Promise<QuizData> => {
    const res = await api.post('/quizzes/generate', {
      document_id: documentId,
      num_questions: numQuestions,
      difficulty,
      question_type: questionType,
      force_regenerate: forceRegenerate,
    });
    return res.data;
  },

  submitQuiz: async (
    quizId: string,
    answers: Record<string, string | string[]>
  ): Promise<QuizData> => {
    const res = await api.post(`/quizzes/${quizId}/submit`, { answers });
    return res.data;
  },

  getRevisionNotes: async (documentId: string): Promise<RevisionNotesData> => {
    const res = await api.get(`/quizzes/notes/${documentId}`);
    return res.data;
  },

  generateRevisionNotes: async (
    documentId: string,
    forceRegenerate = false
  ): Promise<RevisionNotesData> => {
    const res = await api.post('/quizzes/notes/generate', {
      document_id: documentId,
      force_regenerate: forceRegenerate,
    });
    return res.data;
  },
};

export default api;

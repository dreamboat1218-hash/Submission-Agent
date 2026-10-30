import type {
  Health,
  KbDocument,
  KbChapterRule,
  KbChapterRulePreview,
  KbFileNote,
  KbFileSearchResponse,
  KbFileStatus,
  KbFileTag,
  KbFileTreeNode,
  KbSearchResult,
  KbType,
  LoginResponse,
  PackageData,
  SystemSettings,
  Task,
} from './types';

const TOKEN_KEY = 'bid_agent_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body && !(init.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, { ...init, headers });
  if (response.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event('bid-agent:unauthorized'));
    throw new Error('登录已过期，请重新登录');
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<{ id: string; username: string; role: string }>('/api/auth/me'),
  upload: (file: File, options: { autoRun: boolean; mode: string; useKb: boolean; withCheck: boolean; source: string }) => {
    const form = new FormData();
    form.append('file', file);
    const params = new URLSearchParams({
      auto_run: String(options.autoRun),
      mode: options.mode,
      use_kb: String(options.useKb),
      with_check: String(options.withCheck),
      source: options.source,
    });
    return request<Task>(`/api/preprocess?${params.toString()}`, { method: 'POST', body: form });
  },
  runTask: (taskId: string, payload: { mode: string; industry: string; use_kb: boolean; with_check: boolean }) =>
    request<Task>(`/api/tasks/${taskId}/run`, { method: 'POST', body: JSON.stringify(payload) }),
  listTasks: (status?: string, source?: string) => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (source) params.set('source', source);
    const query = params.toString();
    return request<{ total: number; items: Task[] }>(`/api/tasks${query ? `?${query}` : ''}`);
  },
  getTask: (taskId: string) => request<Task>(`/api/tasks/${taskId}`),
  getPackages: (taskId: string) => request<PackageData>(`/api/tasks/${taskId}/packages`),
  parsePackages: (taskId: string) => request<PackageData>(`/api/tasks/${taskId}/packages/parse`, { method: 'POST' }),
  getPackageFile: (taskId: string, path: string) =>
    request<{ name: string; content: string }>(`/api/tasks/${taskId}/package-file?path=${encodeURIComponent(path)}`),
  getPackageFileBlob: async (taskId: string, path: string) => {
    const token = getToken();
    const response = await fetch(`/api/tasks/${taskId}/package-file/raw?path=${encodeURIComponent(path)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) throw new Error('文件读取失败');
    return response.blob();
  },
  getPackageFilePreviewBlob: async (taskId: string, path: string) => {
    const token = getToken();
    const response = await fetch(`/api/tasks/${taskId}/package-file/preview?path=${encodeURIComponent(path)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) throw new Error('预览文件读取失败');
    return response.blob();
  },
  generatePackageBid: (taskId: string, packageNo: string, files: string[], subproject?: string) =>
    request<{
      bid_file_path: string;
      product_count: number;
      package_no: string;
      package_name: string;
      products: string[];
      knowledge_sections?: number;
      knowledge_items?: number;
    }>(`/api/tasks/${taskId}/packages/${encodeURIComponent(packageNo)}/generate`, {
      method: 'POST',
      body: JSON.stringify({ files, subproject }),
    }),
  getPackageBidBlob: async (taskId: string, path: string) => {
    const token = getToken();
    const response = await fetch(`/api/tasks/${taskId}/package-bid?path=${encodeURIComponent(path)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) throw new Error('投标文件读取失败');
    return response.blob();
  },
  deleteTask: (taskId: string) => request<{ ok: boolean }>(`/api/tasks/${taskId}`, { method: 'DELETE' }),
  check: (taskId: string) => request<Task>(`/api/check`, { method: 'POST', body: JSON.stringify({ task_id: taskId }) }),
  kbList: () => request<KbDocument[]>('/api/kb/documents'),
  kbAdd: (payload: { title: string; content: string; doc_type: string; directory?: string; tags?: string[] }) =>
    request<KbDocument>('/api/kb/documents', { method: 'POST', body: JSON.stringify(payload) }),
  kbUpload: (file: File, docType: string, title: string, directory?: string, tags?: string[]) => {
    const form = new FormData();
    form.append('file', file);
    form.append('doc_type', docType);
    if (title.trim()) form.append('title', title.trim());
    if (directory) form.append('directory', directory);
    if (tags?.length) form.append('tags', tags.join(','));
    return request<KbDocument>('/api/kb/upload', { method: 'POST', body: form });
  },
  kbDelete: (id: string) => request<{ ok: boolean }>(`/api/kb/documents/${id}`, { method: 'DELETE' }),
  kbTypes: () => request<KbType[]>('/api/kb/types'),
  kbAddType: (name: string, chapter: string, description: string) =>
    request<KbType>('/api/kb/types', { method: 'POST', body: JSON.stringify({ name, chapter, description }) }),
  kbDeleteType: (id: string) => request<{ ok: boolean }>(`/api/kb/types/${id}`, { method: 'DELETE' }),
  kbSearch: (q: string) => request<{ query: string; results: KbSearchResult[] }>(`/api/kb/search?q=${encodeURIComponent(q)}`),
  kbFilesStatus: () => request<KbFileStatus>('/api/kb-files/status'),
  kbFilesTree: () => request<KbFileTreeNode[]>('/api/kb-files/tree'),
  kbFileNote: (path: string) => request<KbFileNote>(`/api/kb-files/note?path=${encodeURIComponent(path)}`),
  kbFileSave: (path: string, content: string, metadata: Record<string, unknown>) =>
    request<KbFileNote>('/api/kb-files/note', { method: 'POST', body: JSON.stringify({ path, content, metadata }) }),
  kbFilesSearch: (q: string, limit = 5) =>
    request<KbFileSearchResponse>(`/api/kb-files/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  kbFilesTags: () => request<{ tags: KbFileTag[] }>('/api/kb-files/tags'),
  kbFilesNotes: (tag?: string) =>
    request<{ notes: string[] }>(`/api/kb-files/notes${tag ? `?tag=${encodeURIComponent(tag)}` : ''}`),
  kbFilesReindex: () => request<{ ok: boolean; engine: string; message?: string }>('/api/kb-files/reindex', { method: 'POST' }),
  kbChapterRules: () => request<{ rules: KbChapterRule[] }>('/api/kb-files/chapter-rules'),
  kbSaveChapterRules: (rules: KbChapterRule[]) =>
    request<{ rules: KbChapterRule[] }>('/api/kb-files/chapter-rules', { method: 'PUT', body: JSON.stringify({ rules }) }),
  kbDirectories: () => request<{ directories: string[] }>('/api/kb-files/directories'),
  kbPreviewChapterRule: (rule: KbChapterRule, chapterTitle?: string) =>
    request<KbChapterRulePreview>('/api/kb-files/chapter-rules/preview', {
      method: 'POST',
      body: JSON.stringify({ ...rule, chapter_title: chapterTitle }),
    }),
  bidSpecialRules: () => request<{ scope: string; rules: KbChapterRule[] }>('/api/bid-special/chapter-rules'),
  bidSaveSpecialRules: (rules: KbChapterRule[]) =>
    request<{ scope: string; rules: KbChapterRule[] }>('/api/bid-special/chapter-rules', {
      method: 'PUT',
      body: JSON.stringify({ rules }),
    }),
  bidResetSpecialRules: () =>
    request<{ scope: string; rules: KbChapterRule[] }>('/api/bid-special/chapter-rules/reset', { method: 'POST' }),
  bidPreviewSpecialRule: (rule: KbChapterRule, chapterTitle?: string) =>
    request<KbChapterRulePreview>('/api/bid-special/chapter-rules/preview', {
      method: 'POST',
      body: JSON.stringify({ ...rule, chapter_title: chapterTitle }),
    }),
  settings: () => request<SystemSettings>('/api/settings'),
  updateSettings: (payload: {
    tender_extract_url?: string;
    tender_extract_api_key?: string;
    tender_llm_provider?: string;
    tender_llm_model?: string;
    tender_llm_api_key?: string;
    tender_llm_base_url?: string;
    tender_llm_providers?: Array<{
      provider: string;
      model: string;
      api_key?: string;
      base_url?: string;
    }>;
    biaoshu_skill_path?: string;
  }) => request<SystemSettings>('/api/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  health: () => request<Health>('/api/health'),
};

export async function downloadBid(taskId: string): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api/download/${taskId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) throw new Error('下载失败');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `投标文件_${taskId.slice(0, 8)}.docx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function taskProgressUrl(taskId: string): string {
  const token = getToken();
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/task/${taskId}?token=${encodeURIComponent(token ?? '')}`;
}

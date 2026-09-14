export interface User {
  id: string;
  username: string;
  role: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface Task {
  id: string;
  user_id: string;
  status: string;
  current_stage: string;
  progress: number;
  message: string;
  original_file_name: string;
  file_count: number;
  manifest: Manifest | null;
  extracted_data: ExtractedData | null;
  industry: string;
  bid_file_path: string;
  check_result: ComplianceReport | null;
  mode: string;
  source: string;
  error_message: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface Manifest {
  task_id: string;
  file_count: number;
  files: ManifestFile[];
  warnings: string[];
  conflicts: string[];
}

export interface ManifestFile {
  path: string;
  rel_path: string;
  type: string;
  size: number;
  md_path: string;
  page_count: number;
  status: string;
  warnings: string[];
}

export interface FieldValue {
  primary_value: string | number | string[] | Record<string, unknown>;
  confidence: number;
  evidence: {
    source_file: string;
    page: number;
    text: string;
  };
}

export interface ExtractedData {
  [field: string]: FieldValue | Meta | undefined;
  _meta?: Meta;
}

export interface Meta {
  mode: string;
  provider: string;
  source_files: string[];
  confidence_summary: {
    high: number;
    medium: number;
    low: number;
  };
  llm_calls: number;
  field_count: number;
}

export interface ComplianceItem {
  name: string;
  result: 'PASS' | 'WARN' | 'FAIL';
  detail: string;
  suggestion: string | null;
}

export interface ComplianceReport {
  status: 'PASS' | 'WARN' | 'FAIL';
  check_time: string;
  task_id: string;
  items: ComplianceItem[];
  summary: {
    total: number;
    pass: number;
    warn: number;
    fail: number;
  };
}

export interface ProgressMessage {
  task_id: string;
  progress: number;
  message: string;
  status: string;
  stage: string;
  estimated_time_remaining: number;
}

export interface KbDocument {
  id: string;
  title: string;
  content: string;
  doc_type: string;
  metadata: Record<string, unknown> | null;
  file_path: string;
  created_at: string;
  updated_at: string;
}

export interface KbSearchResult {
  id: string;
  title: string;
  content: string;
  doc_type: string;
  score: number;
}

export interface KbType {
  id: string;
  name: string;
  chapter: string;
  description: string;
  builtin?: boolean;
}

export interface KbFileStatus {
  root_path: string;
  config_path?: string;
  notes_count: number;
  pinakes_available: boolean;
  pinakes_bin: string;
  index_exists: boolean;
  fallback_on_error: boolean;
  max_search_results: number;
  search_timeout: number;
  directories: Record<string, string>;
}

export interface KbFileTreeNode {
  name: string;
  path: string;
  type: 'dir' | 'file';
  children?: KbFileTreeNode[];
}

export interface KbFileNote {
  path: string;
  content: string;
  metadata: Record<string, unknown>;
}

export interface KbFileSearchResult {
  path: string;
  score: number;
  content: string;
  metadata: Record<string, unknown>;
  engine?: string;
  source?: string;
}

export interface KbFileSearchResponse {
  query: string;
  engine: string;
  results: KbFileSearchResult[];
}

export interface KbFileTag {
  tag: string;
  count: number;
}

export interface KbChapterRule {
  keywords: string[];
  directories: string[];
  tags: string[];
  frontmatter?: string[];
  query: string;
  max_items: number;
}

export interface KbChapterRulePreview {
  title: string;
  items: KbFileSearchResult[];
}

export interface SystemSettings {
  app_name: string;
  system_env: string;
  llm_provider: string;
  tender_extract_url: string;
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
  biaoshu_skill_path: string;
  use_vector_search: boolean;
  max_file_size: number;
  max_extract_depth: number;
  max_files_per_task: number;
}

export interface Health {
  status: string;
  version: string;
  services: Record<string, string>;
}

export interface PackageFile {
  name: string;
  rel_path: string;
  size: number;
  kind: 'tech_spec' | 'tender_doc' | 'other';
  md_path: string;
  source_path?: string;
  content_preview: string;
  has_tech_params?: boolean;
  tech_spec_code?: string;
}

export interface ScoreRuleItem {
  项目: string;
  评审要素: string;
  评审内容: string;
}

export interface PackageItem {
  package_no: string;
  package_name: string;
  subproject_name: string;
  subproject_number: string;
  subproject_dir?: string;
  tech_spec_code: string;
  tech_spec_codes?: string[];
  '项目名称'?: string;
  '项目编号'?: string;
  '招标编号'?: string;
  '分标名称'?: string;
  '分标编号'?: string;
  '包名称'?: string;
  '包号'?: string;
  '技术规范编码'?: string;
  技术评分规则?: ScoreRuleItem[];
  专用资格要求?: Record<string, string> | null;
  评分权重?: Record<string, string> | null;
  source_archive: string;
  warnings: string[];
  files: PackageFile[];
  meta: Record<string, string>;
}

export interface SubprojectItem {
  '分标名称': string;
  '分标编号': string;
  '项目名称': string;
  '项目编号': string;
  '招标编号'?: string;
  '包名称'?: string;
  '包号'?: string;
  技术评分规则?: ScoreRuleItem[];
  专用资格要求?: Record<string, string> | null;
  评分权重?: Record<string, string> | null;
  source_dir: string;
  packages: PackageItem[];
}

export interface PackageData {
  task_id: string;
  project: Record<string, string>;
  packages: PackageItem[];
  subprojects?: SubprojectItem[];
  warnings: string[];
}

import { Fragment, useEffect, useState } from 'react';
import { BookOpen, Check, Copy, FileUp, FileText, FolderPlus, Plus, RefreshCw, Save, Search, Settings2, Tag, Trash2 } from 'lucide-react';
import { api } from '../api';
import type { KbChapterRule, KbChapterRulePreview, KbDocument, KbFileNote, KbFileSearchResponse, KbFileStatus, KbFileTag, KbFileTreeNode } from '../types';
import { EmptyState } from '../components/StatusBadge';

export function Knowledge() {
  const [docs, setDocs] = useState<KbDocument[]>([]);
  const [query, setQuery] = useState('');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [message, setMessage] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadDir, setUploadDir] = useState('');
  const [uploadTags, setUploadTags] = useState('');
  const [docDir, setDocDir] = useState('');
  const [docTags, setDocTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [kbStatus, setKbStatus] = useState<KbFileStatus | null>(null);
  const [kbTree, setKbTree] = useState<KbFileTreeNode[]>([]);
  const [kbTags, setKbTags] = useState<KbFileTag[]>([]);
  const [activeNote, setActiveNote] = useState<KbFileNote | null>(null);
  const [noteContent, setNoteContent] = useState('');
  const [noteMetadata, setNoteMetadata] = useState('');
  const [fileQuery, setFileQuery] = useState('');
  const [fileResults, setFileResults] = useState<KbFileSearchResponse | null>(null);
  const [selectedTag, setSelectedTag] = useState('');
  const [tagNotes, setTagNotes] = useState<string[]>([]);
  const [kbMessage, setKbMessage] = useState('');
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState(false);
  const [ruleDrafts, setRuleDrafts] = useState<{ keywords: string; directories: string[]; tags: string; frontmatter: string; query: string; max_items: number }[]>([]);
  const [kbDirs, setKbDirs] = useState<string[]>([]);
  const [previews, setPreviews] = useState<Record<number, KbChapterRulePreview>>({});
  const [kbTab, setKbTab] = useState<'all' | 'library' | 'obsidian' | 'rules'>('all');

  const load = () =>
    Promise.all([
      api.kbList().then(setDocs),
    ]);

  useEffect(() => {
    void load();
    void loadObsidian();
    void loadChapterRules();
  }, []);

  const loadObsidian = () =>
    Promise.all([
      api.kbFilesStatus().then(setKbStatus),
      api.kbFilesTree().then(setKbTree),
      api.kbFilesTags().then((data) => setKbTags(data.tags)),
      api.kbDirectories().then((data) => setKbDirs(data.directories)),
    ]);

  const toggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const openNote = async (path: string) => {
    try {
      const note = await api.kbFileNote(path);
      setActiveNote(note);
      setNoteContent(note.content);
      setNoteMetadata(JSON.stringify(note.metadata ?? {}, null, 2));
      setKbMessage('');
    } catch (err) {
      setKbMessage(err instanceof Error ? err.message : '读取笔记失败');
    }
  };

  const saveNote = async () => {
    if (!activeNote) return;
    let metadata: Record<string, unknown> = {};
    try {
      metadata = noteMetadata.trim() ? JSON.parse(noteMetadata) : {};
    } catch {
      setKbMessage('Frontmatter 元数据不是合法 JSON');
      return;
    }
    try {
      const saved = await api.kbFileSave(activeNote.path, noteContent, metadata);
      setActiveNote(saved);
      setKbMessage('已保存');
      await loadObsidian();
    } catch (err) {
      setKbMessage(err instanceof Error ? err.message : '保存失败');
    }
  };

  const searchFiles = async () => {
    if (!fileQuery.trim()) return;
    try {
      const result = await api.kbFilesSearch(fileQuery);
      setFileResults(result);
      setSelectedTag('');
      setTagNotes([]);
    } catch (err) {
      setKbMessage(err instanceof Error ? err.message : '检索失败');
    }
  };

  const selectTag = async (tag: string) => {
    setSelectedTag(tag);
    setFileResults(null);
    try {
      const data = await api.kbFilesNotes(tag);
      setTagNotes(data.notes);
    } catch (err) {
      setKbMessage(err instanceof Error ? err.message : '标签检索失败');
    }
  };

  const renderTree = (nodes: KbFileTreeNode[], depth = 0) =>
    nodes.map((node) => (
      <div key={node.path} className="obs-tree-item" style={{ paddingLeft: `${depth * 16 + 6}px` }}>
        {node.type === 'dir' ? (
          <button className="obs-tree-dir" onClick={() => toggleDir(node.path)}>
            <FolderPlus size={14} />
            {node.name}
          </button>
        ) : (
          <button className="obs-tree-file" onClick={() => void openNote(node.path)}>
            <FileText size={14} />
            {node.name}
          </button>
        )}
        {node.type === 'dir' && expandedDirs.has(node.path) && node.children ? renderTree(node.children, depth + 1) : null}
      </div>
    ));

  const copyKbPath = async () => {
    if (!kbStatus) return;
    try {
      await navigator.clipboard.writeText(kbStatus.root_path);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setKbMessage('复制失败，请手动复制路径');
    }
  };

  const loadChapterRules = async () => {
    try {
      const data = await api.kbChapterRules();
      setRuleDrafts(data.rules.map((rule) => ({
        keywords: rule.keywords.join('、'),
        directories: rule.directories,
        tags: rule.tags.join('、'),
        frontmatter: (rule.frontmatter ?? []).join('、'),
        query: rule.query,
        max_items: rule.max_items,
      })));
    } catch (err) {
      setKbMessage(err instanceof Error ? err.message : '规则读取失败');
    }
  };

  const updateRule = (index: number, field: string, value: string | number | string[]) => {
    setRuleDrafts((current) => current.map((rule, i) => (i === index ? { ...rule, [field]: value } : rule)));
  };

  const addRule = () => {
    setRuleDrafts((current) => [...current, { keywords: '', directories: [], tags: '', frontmatter: '', query: '', max_items: 3 }]);
  };

  const removeRule = (index: number) => {
    setRuleDrafts((current) => current.filter((_, i) => i !== index));
  };

  const saveChapterRules = async () => {
    const split = (value: string) => value.split(/[、,，;；]/).map((item) => item.trim()).filter(Boolean);
    const rules: KbChapterRule[] = ruleDrafts
      .filter((rule) => rule.keywords.trim())
      .map((rule) => ({
        keywords: split(rule.keywords),
        directories: rule.directories,
        tags: split(rule.tags),
        frontmatter: split(rule.frontmatter),
        query: rule.query.trim(),
        max_items: Math.max(1, Math.min(20, Number(rule.max_items) || 3)),
      }));
    try {
      const saved = await api.kbSaveChapterRules(rules);
      setRuleDrafts(saved.rules.map((rule) => ({
        keywords: rule.keywords.join('、'),
        directories: rule.directories,
        tags: rule.tags.join('、'),
        frontmatter: (rule.frontmatter ?? []).join('、'),
        query: rule.query,
        max_items: rule.max_items,
      })));
      setKbMessage('章节映射规则已保存');
    } catch (err) {
      setKbMessage(err instanceof Error ? err.message : '规则保存失败');
    }
  };

  const previewRule = async (index: number) => {
    const draft = ruleDrafts[index];
    if (!draft?.keywords.trim()) return;
    const split = (value: string) => value.split(/[、,，;；]/).map((item) => item.trim()).filter(Boolean);
    const rule: KbChapterRule = {
      keywords: split(draft.keywords),
      directories: draft.directories,
      tags: split(draft.tags),
      frontmatter: split(draft.frontmatter),
      query: draft.query.trim(),
      max_items: Math.max(1, Math.min(20, Number(draft.max_items) || 3)),
    };
    try {
      const result = await api.kbPreviewChapterRule(rule, split(draft.keywords)[0]);
      setPreviews((current) => ({ ...current, [index]: result }));
      setKbMessage('');
    } catch (err) {
      setKbMessage(err instanceof Error ? err.message : '试检索失败');
    }
  };

  const add = async () => {
    if (!title.trim()) return;
    setMessage('');
    try {
      await api.kbAdd({ title, content, doc_type: dirToType(docDir), directory: docDir || undefined, tags: splitTags(docTags) });
      setTitle('');
      setContent('');
      setDocDir('');
      setDocTags('');
      load();
      setMessage('已添加');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '添加失败');
    }
  };

  const remove = async (id: string) => {
    await api.kbDelete(id);
    load();
  };

  const splitTags = (value: string) =>
    value
      .split(/[、,，;；]/)
      .map((tag) => tag.trim())
      .filter(Boolean);

  const dirToType = (directory: string) => {
    const mapping: Record<string, string> = {
      '01_企业资质': '企业资质',
      '02_历史标书': '历史标书',
      '05_投标模板': '模板库',
      _system_generated: 'FAQ',
    };
    return mapping[directory] ?? '企业资质';
  };

  const upload = async () => {
    if (!uploadFile || uploading) return;
    setUploading(true);
    setMessage('');
    try {
      await api.kbUpload(uploadFile, dirToType(uploadDir), uploadTitle, uploadDir || undefined, splitTags(uploadTags));
      setUploadFile(null);
      setUploadTitle('');
      setUploadDir('');
      setUploadTags('');
      load();
      setMessage('附件已上传并完成章节识别');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const search = async () => {
    if (!query.trim()) {
      load();
      return;
    }
    const result = await api.kbSearch(query);
    setDocs(
      result.results.map((item) => ({
        id: item.id,
        title: item.title,
        content: item.content,
        doc_type: item.doc_type,
        metadata: null,
        file_path: '',
        created_at: '',
        updated_at: '',
      })),
    );
  };

  const searchAll = async () => {
    if (!query.trim()) {
      await load();
      return;
    }
    await Promise.all([search(), searchFiles()]);
  };

  const flattenNotes = (nodes: KbFileTreeNode[]): KbFileTreeNode[] =>
    nodes.flatMap((node) => (node.type === 'file' ? [node] : node.children ? flattenNotes(node.children) : []));

  const unifiedItems = () => {
    const notes = flattenNotes(kbTree);
    const noteNames = new Set(notes.map((node) => node.path.split('/').pop()?.replace(/\.md$/i, '') ?? ''));
    const libraryOnly = docs.filter((doc) => !noteNames.has(doc.title));
    return [
      ...notes.map((node) => ({ key: `note:${node.path}`, title: node.path, source: 'Obsidian', path: node.path, doc: null })),
      ...libraryOnly.map((doc) => ({ key: `doc:${doc.id}`, title: doc.title, source: doc.doc_type, path: '', doc })),
    ];
  };

  const openObsidianFromAll = async (path: string) => {
    setKbTab('obsidian');
    await openNote(path);
  };

  return (
    <div className="knowledge-page">
      <section className="panel kb-unified">
        <div className="panel-header">
          <h2>
            <BookOpen size={16} />
            知识库
          </h2>
          <div className="obs-actions">
            <button className="button button-ghost" onClick={() => { void load(); void loadObsidian(); }}>
              <RefreshCw size={15} />
              刷新
            </button>
            <button className="button button-ghost" onClick={() => void api.kbFilesReindex()}>
              <RefreshCw size={15} />
              重建索引
            </button>
          </div>
        </div>
        <div className="kb-tabs">
          {(
            [
              ['all', '全部'],
              ['library', '资料库'],
              ['obsidian', 'Obsidian 文件库'],
              ['rules', '章节知识映射'],
            ] as const
          ).map(([key, label]) => (
            <button key={key} className={`kb-tab ${kbTab === key ? 'kb-tab-active' : ''}`} onClick={() => setKbTab(key)}>
              {label}
            </button>
          ))}
        </div>

        {kbTab === 'all' && (
          <div className="kb-all">
            <div className="obs-search">
              <Search size={15} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void searchAll();
                }}
                placeholder="统一检索资料库与 Obsidian 笔记"
              />
              <button className="button button-ghost" onClick={() => void searchAll()}>检索</button>
            </div>
            {fileResults ? (
              <div className="obs-results">
                <div className="obs-engine">引擎：{fileResults.engine === 'pinakes' ? 'Pinakes 语义检索' : fileResults.engine === 'keyword' ? '关键词匹配' : '无结果'}</div>
                {fileResults.results.map((item) => (
                  <button key={item.path} className="obs-result" onClick={() => void openObsidianFromAll(item.path)}>
                    <strong>{item.path}</strong>
                    <span>相关度 {item.score.toFixed(2)}</span>
                    <p>{item.content.slice(0, 120)}</p>
                  </button>
                ))}
              </div>
            ) : unifiedItems().length === 0 ? (
              <EmptyState icon={<BookOpen size={34} />} title="暂无知识内容" />
            ) : (
              <div className="kb-list">
                {unifiedItems().map((item) => (
                  <div
                    className="kb-item"
                    key={item.key}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      if (item.path) void openObsidianFromAll(item.path);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && item.path) void openObsidianFromAll(item.path);
                    }}
                  >
                    <div className="kb-item-head">
                      <span className="kb-type">{item.source}</span>
                      {!item.path && item.doc?.metadata?.chapter ? <span className="kb-type kb-chapter">{String(item.doc.metadata.chapter)}</span> : null}
                      <strong>{item.title}</strong>
                      {!item.path && item.doc ? (
                        <button
                          className="icon-button icon-button-danger"
                          title="删除"
                          onClick={(event) => {
                            event.stopPropagation();
                            void remove(item.doc?.id ?? '');
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      ) : null}
                    </div>
                    <p>{!item.path && item.doc ? item.doc.content : item.title}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {kbTab === 'library' && (
          <div className="knowledge-layout">
            <section className="panel kb-form-panel">
        <div className="panel-header">
          <h2>附件上传</h2>
        </div>
        <label className="field">
          <span>附件</span>
          <input type="file" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
        </label>
        <label className="field">
          <span>标题</span>
          <input value={uploadTitle} onChange={(event) => setUploadTitle(event.target.value)} placeholder="留空自动取文件名" />
        </label>
        <label className="field">
          <span>知识库目录</span>
          <select value={uploadDir} onChange={(event) => setUploadDir(event.target.value)}>
            <option value="">自动识别</option>
            {kbDirs.map((dir) => (
              <option key={dir} value={dir}>{dir}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>标签</span>
          <input list="kb-tags-list" value={uploadTags} onChange={(event) => setUploadTags(event.target.value)} placeholder="如：资质、认证" />
        </label>
        <button className="button button-primary button-block" onClick={() => void upload()} disabled={!uploadFile || uploading}>
          <FileUp size={16} />
          {uploading ? '上传解析中…' : '上传附件'}
        </button>
        <div className="divider" />
        <div className="panel-header">
          <h2>文本资料</h2>
        </div>
        <label className="field">
          <span>标题</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label className="field">
          <span>知识库目录</span>
          <select value={docDir} onChange={(event) => setDocDir(event.target.value)}>
            <option value="">默认（企业资质）</option>
            {kbDirs.map((dir) => (
              <option key={dir} value={dir}>{dir}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>标签</span>
          <input list="kb-tags-list" value={docTags} onChange={(event) => setDocTags(event.target.value)} placeholder="如：资质、认证" />
        </label>
        <label className="field">
          <span>内容</span>
          <textarea rows={9} value={content} onChange={(event) => setContent(event.target.value)} />
        </label>
        <button className="button button-secondary button-block" onClick={() => void add()}>
          <Plus size={16} />
          添加文本
        </button>
        {message && <div className="form-note">{message}</div>}
      </section>

        <section className="panel">
        <div className="panel-header">
          <h2>知识库</h2>
          <div className="search-box">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void search();
              }}
              placeholder="检索"
            />
            <button className="button button-ghost" onClick={() => void search()}>检索</button>
          </div>
        </div>
        {docs.length === 0 ? (
          <EmptyState icon={<Search size={34} />} title="暂无知识库资料" />
        ) : (
          <div className="kb-list">
            {docs.map((doc) => (
              <div className="kb-item" key={doc.id}>
                <div className="kb-item-head">
                  <span className="kb-type">{doc.doc_type}</span>
                  {doc.metadata?.chapter ? <span className="kb-type kb-chapter">{String(doc.metadata.chapter)}</span> : null}
                  <strong>{doc.title}</strong>
                  <button className="icon-button icon-button-danger" title="删除" onClick={() => void remove(doc.id)}>
                    <Trash2 size={15} />
                  </button>
                </div>
                <p>{doc.content}</p>
              </div>
            ))}
          </div>
        )}
        </section>
        </div>
        )}

        {kbTab === 'obsidian' && (
          <section className="panel obsidian-panel">
        <div className="panel-header">
          <h2>
            <BookOpen size={16} />
            Obsidian 知识库
          </h2>
          <div className="obs-actions">
            <span className={`obs-badge ${kbStatus?.pinakes_available ? 'obs-badge-ok' : 'obs-badge-warn'}`}>
              {kbStatus?.pinakes_available ? '语义检索可用' : '关键词检索降级'}
            </span>
            <button className="button button-ghost" onClick={() => void loadObsidian()}>
              <RefreshCw size={15} />
              刷新
            </button>
            <button className="button button-ghost" onClick={() => void api.kbFilesReindex()}>
              <RefreshCw size={15} />
              重建索引
            </button>
          </div>
        </div>
        {kbStatus ? (
          <div className="obs-status">
            <div className="obs-dir">
              <span className="obs-dir-label">当前知识库目录</span>
              <code className="obs-dir-path">{kbStatus.root_path}</code>
              <button className="icon-button" title="复制路径" onClick={() => void copyKbPath()}>
                {copied ? <Check size={15} /> : <Copy size={15} />}
              </button>
            </div>
            <span>配置：{kbStatus.config_path ?? 'config.yaml'}</span>
            <span>笔记：{kbStatus.notes_count} 篇</span>
            <span>索引：{kbStatus.index_exists ? '已创建' : '未创建'}</span>
            <span>Pinakes：{kbStatus.pinakes_bin}</span>
          </div>
        ) : null}
        <div className="obs-layout">
          <div className="obs-column">
            <div className="obs-search">
              <Search size={15} />
              <input
                value={fileQuery}
                onChange={(event) => setFileQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void searchFiles();
                }}
                placeholder="语义/关键词检索"
              />
              <button className="button button-ghost" onClick={() => void searchFiles()}>检索</button>
            </div>
            {fileResults && (
              <div className="obs-results">
                <div className="obs-engine">引擎：{fileResults.engine === 'pinakes' ? 'Pinakes 语义检索' : fileResults.engine === 'keyword' ? '关键词匹配' : '无结果'}</div>
                {fileResults.results.map((item) => (
                  <button key={item.path} className="obs-result" onClick={() => void openNote(item.path)}>
                    <strong>{item.path}</strong>
                    <span>相关度 {item.score.toFixed(2)}</span>
                    <p>{item.content.slice(0, 120)}</p>
                  </button>
                ))}
              </div>
            )}
            {selectedTag && (
              <div className="obs-results">
                <div className="obs-engine">标签：{selectedTag}（{tagNotes.length} 篇）</div>
                {tagNotes.map((path) => (
                  <button key={path} className="obs-result" onClick={() => void openNote(path)}>
                    <strong>{path}</strong>
                  </button>
                ))}
              </div>
            )}
            <div className="obs-tags">
              {kbTags.map((item) => (
                <button key={item.tag} className={`obs-tag ${selectedTag === item.tag ? 'obs-tag-active' : ''}`} onClick={() => void selectTag(item.tag)}>
                  <Tag size={12} />
                  {item.tag}（{item.count}）
                </button>
              ))}
            </div>
            <div className="obs-tree">{renderTree(kbTree)}</div>
          </div>
          <div className="obs-column">
            {activeNote ? (
              <>
                <div className="obs-note-head">
                  <strong>{activeNote.path}</strong>
                  <button className="button button-secondary" onClick={() => void saveNote()}>
                    <Save size={15} />
                    保存
                  </button>
                </div>
                <label className="field">
                  <span>Frontmatter（JSON）</span>
                  <textarea rows={5} value={noteMetadata} onChange={(event) => setNoteMetadata(event.target.value)} />
                </label>
                <label className="field">
                  <span>正文（Markdown）</span>
                  <textarea rows={18} value={noteContent} onChange={(event) => setNoteContent(event.target.value)} />
                </label>
              </>
            ) : (
              <EmptyState icon={<BookOpen size={34} />} title="从左侧选择或检索一篇笔记" />
            )}
            {kbMessage && <div className="form-note">{kbMessage}</div>}
          </div>
        </div>
        </section>
        )}

        {kbTab === 'rules' && (
          <section className="panel rules-panel">
        <div className="panel-header">
          <h2>
            <Settings2 size={16} />
            章节知识映射
          </h2>
          <div className="obs-actions">
            <button className="button button-ghost" onClick={() => void loadChapterRules()}>
              <RefreshCw size={15} />
              重置
            </button>
            <button className="button button-secondary" onClick={addRule}>
              <Plus size={15} />
              新增映射
            </button>
            <button className="button button-primary" onClick={() => void saveChapterRules()}>
              <Save size={15} />
              保存映射
            </button>
          </div>
        </div>
        <p className="panel-hint">章节标题命中关键词时，自动从对应的知识库目录/标签/语义检索中取内容，追加到该章节的“知识库参考内容”。</p>
        <datalist id="kb-tags-list">
          {kbTags.map((item) => (
            <option key={item.tag} value={item.tag} />
          ))}
        </datalist>
        <div className="rules-table-wrap">
          <table className="rules-table">
            <thead>
              <tr>
                <th className="col-keywords">章节关键词</th>
                <th className="col-dirs">知识库目录</th>
                <th className="col-tags">标签</th>
                <th className="col-frontmatter">Frontmatter 字段</th>
                <th className="col-query">检索词</th>
                <th className="col-count">条数</th>
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {ruleDrafts.map((rule, index) => (
                <Fragment key={index}>
                  <tr>
                    <td>
                      <input value={rule.keywords} onChange={(event) => updateRule(index, 'keywords', event.target.value)} placeholder="如：资质证明、资格文件" />
                    </td>
                    <td>
                      <select
                        className="rule-dir-select"
                        value={rule.directories[0] ?? ''}
                        onChange={(event) =>
                          updateRule(index, 'directories', event.target.value ? [event.target.value] : [])
                        }
                      >
                        <option value="">请选择知识库目录</option>
                        {kbDirs.map((dir) => (
                          <option key={dir} value={dir}>
                            {dir}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input list="kb-tags-list" value={rule.tags} onChange={(event) => updateRule(index, 'tags', event.target.value)} placeholder="如：资质、营业执照" />
                    </td>
                    <td>
                      <input value={rule.frontmatter} onChange={(event) => updateRule(index, 'frontmatter', event.target.value)} placeholder="如：industry:IT、status:已中标" />
                    </td>
                    <td>
                      <input value={rule.query} onChange={(event) => updateRule(index, 'query', event.target.value)} placeholder="如：营业执照 ISO 认证 资质" />
                    </td>
                    <td>
                      <input type="number" min={1} max={20} value={rule.max_items} onChange={(event) => updateRule(index, 'max_items', Number(event.target.value))} />
                    </td>
                    <td>
                      <div className="rule-actions">
                        <button className="button button-ghost" title="试检索" onClick={() => void previewRule(index)}>
                          <Search size={14} />
                        </button>
                        <button className="icon-button icon-button-danger" title="删除映射" onClick={() => removeRule(index)}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {previews[index] && (
                    <tr className="rule-preview-row">
                      <td colSpan={6}>
                        <div className="rule-preview">
                          <div className="obs-engine">试检索：{previews[index].title}（命中 {previews[index].items.length} 条）</div>
                          {previews[index].items.length === 0 ? (
                            <div className="form-note">未命中知识笔记，请检查目录/标签/检索词</div>
                          ) : (
                            previews[index].items.map((item) => (
                              <div className="rule-preview-item" key={item.path}>
                                <strong>{item.path}</strong>
                                <span>{item.source ?? item.engine ?? '知识库'} · 相关度 {item.score.toFixed(2)}</span>
                                <p>{item.content?.slice(0, 140)}</p>
                              </div>
                            ))
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        </section>
        )}
      </section>
    </div>
  );
}

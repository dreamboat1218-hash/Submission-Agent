import { useEffect, useState } from 'react';
import { Archive, FileText, Layers, RefreshCw } from 'lucide-react';
import { api } from '../api';
import type { FieldValue, PackageData, PackageFile, PackageItem, SubprojectItem, Task } from '../types';
import { EmptyState, ResultBadge, StatusBadge } from '../components/StatusBadge';
import { splitKeyText } from '../utils/keyFormat';

const FIELD_LABELS: Record<string, string> = {
  project_name: '项目名称',
  bid_number: '招标编号',
  budget: '项目预算/最高限价',
  bid_deadline: '投标截止时间',
  bid_opening_time: '开标时间',
  bid_location: '开标地点',
  qualifications: '资质要求列表',
  evaluation_criteria: '评标办法',
  performance_requirements: '业绩要求',
  technical_requirements: '技术要求',
  contact_person: '联系人',
  contact_phone: '联系电话',
  contact_email: '联系邮箱',
  bid_security_amount: '投标保证金金额',
  bid_security_deadline: '保证金缴纳截止时间',
  bid_validity_period: '投标有效期',
  tenderer: '招标人名称',
  tenderer_address: '招标人地址',
  agency_name: '招标代理机构名称',
  agency_contact: '代理机构联系人',
  project_scale: '项目规模',
  delivery_period: '交付/工期要求',
  quality_standard: '质量标准',
  payment_terms: '付款方式',
  bid_format_requirements: '标书格式要求',
};

const KEY_FIELDS: Record<string, string> = {
  project_name: '项目名称',
  bid_number: '招标编号',
  budget: '项目预算/最高限价',
  bid_deadline: '投标截止时间',
  bid_opening_time: '开标时间',
  bid_location: '开标地点',
  tenderer: '招标人名称',
  agency_name: '招标代理机构',
  contact_person: '联系人',
  contact_phone: '联系电话',
  contact_email: '联系邮箱',
  bid_security_amount: '投标保证金金额',
  bid_validity_period: '投标有效期',
  qualifications: '资质要求',
  performance_requirements: '业绩要求',
  evaluation_criteria: '评标办法',
  delivery_period: '交付/工期要求',
  quality_standard: '质量标准',
  payment_terms: '付款方式',
  warranty: '质保期/质保要求',
};

const REFERENCE_RE = /见投标人须知前附表|见招标公告|见招标文件|详见招标公告|详见招标文件|以招标文件为准|同投标文件递交截止时间|同投标截止时间/;

interface QualificationStructured {
  product_table: { columns: string[]; rows: string[][] };
  enterprise: string[];
  bidder: string[];
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function markdownToHtml(markdown: string): string {
  const lines = markdown.split('\n');
  const parts: string[] = [];
  let tableLines: string[] = [];

  const flushTable = () => {
    if (tableLines.length < 2) {
      parts.push(...tableLines.map((line) => `<p>${escapeHtml(line)}</p>`));
      tableLines = [];
      return;
    }
    const rows = tableLines.filter((line) => !/^\s*\|[\s:\-|]+\|\s*$/.test(line));
    const header = rows[0];
    const body = rows.slice(1);
    const cells = (row: string) => row.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((cell) => escapeHtml(cell.trim()));
    parts.push(
      `<table><thead><tr>${cells(header).map((cell) => `<th>${cell}</th>`).join('')}</tr></thead><tbody>${body
        .map((row) => `<tr>${cells(row).map((cell) => `<td>${cell}</td>`).join('')}</tr>`)
        .join('')}</tbody></table>`,
    );
    tableLines = [];
  };

  for (const line of lines) {
    if (line.startsWith('|')) {
      tableLines.push(line);
      continue;
    }
    flushTable();
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith('### ')) parts.push(`<h3>${escapeHtml(trimmed.slice(4))}</h3>`);
    else if (trimmed.startsWith('## ')) parts.push(`<h2>${escapeHtml(trimmed.slice(3))}</h2>`);
    else if (trimmed.startsWith('# ')) parts.push(`<h1>${escapeHtml(trimmed.slice(2))}</h1>`);
    else parts.push(`<p>${escapeHtml(trimmed)}</p>`);
  }
  flushTable();
  return parts.join('');
}

function PackageCard({
  pkg,
  task,
  project,
  subprojectDir,
  selectedFile,
  onSelectFile,
}: {
  pkg: PackageItem;
  task: Task;
  project: Record<string, string>;
  subprojectDir?: string;
  selectedFile: PackageFile | null;
  onSelectFile: (file: PackageFile) => void;
}) {
  const specs = pkg.files.filter((file) => file.kind === 'tech_spec');
  const [selected, setSelected] = useState<string[]>(specs.map((file) => file.md_path));
  const [generated, setGenerated] = useState<{
    bid_file_path: string;
    product_count: number;
    knowledge_sections?: number;
    knowledge_items?: number;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = (mdPath: string) => {
    setSelected((current) => (current.includes(mdPath) ? current.filter((item) => item !== mdPath) : [...current, mdPath]));
  };

  const generate = async () => {
    if (!selected.length || busy) return;
    setBusy(true);
    try {
      const result = await api.generatePackageBid(task.id, pkg['包号'] || pkg.package_no, selected, subprojectDir);
      setGenerated(result);
    } catch {
      setGenerated(null);
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    if (!generated) return;
    const blob = await api.getPackageBidBlob(task.id, generated.bid_file_path);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `投标文件_${pkg['包号'] || pkg.package_no}.docx`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="package-card">
      <div className="package-card-head">
        <Archive size={17} />
        <strong>{pkg['包名称'] || pkg['包号']}</strong>
        <span className="kb-type kb-chapter">{pkg['包号'] || pkg.package_no}</span>
        <span className="subproject-count">{specs.length} 款产品</span>
      </div>
      <span className="panel-hint">{project['项目名称'] ? `项目：${project['项目名称']}` : ''}</span>
      <div className="package-select">
        <span>选择投标产品</span>
        {specs.map((file) => (
          <label className="spec-check" key={file.md_path}>
            <input type="checkbox" checked={selected.includes(file.md_path)} onChange={() => toggle(file.md_path)} />
            <span>{file.name}</span>
          </label>
        ))}
      </div>
      <div className="package-actions">
        <button className="button button-primary" onClick={() => void generate()} disabled={!selected.length || busy}>
          生成该包投标文件
        </button>
        {generated && (
          <button className="button button-secondary" onClick={() => void download()}>
            下载投标文件（{generated.product_count} 款产品）
          </button>
        )}
      </div>
      {generated && (generated.knowledge_sections ?? 0) > 0 && (
        <span className="form-note">已按国网投标映射规则自动填充 {generated.knowledge_sections} 个知识库章节</span>
      )}
      <div className="package-files">
        {specs.map((file) => (
          <div
            className={`package-file package-file-spec ${selectedFile?.md_path === file.md_path ? 'package-file-selected' : ''}`}
            key={file.rel_path}
            role="button"
            tabIndex={0}
            onClick={() => onSelectFile(file)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onSelectFile(file);
            }}
          >
            <FileText size={15} />
            <div>
              {file.tech_spec_code && <span className="spec-code">技术规范编码：{file.tech_spec_code}</span>}
              <strong>{file.name}</strong>
              <span>{file.has_tech_params ? '技术规范书 · 含技术特性参数表' : '技术规范书'}</span>
              <p>{file.content_preview || '（无文本内容）'}</p>
            </div>
          </div>
        ))}
      </div>
      {pkg['技术评分规则']?.length ? (
        <details className="score-rules">
          <summary>技术评分规则（{pkg['技术评分规则'].length} 条）</summary>
          <div className="table-wrap">
            <table className="data-table score-rules-table">
              <thead>
                <tr>
                  <th>项目</th>
                  <th>评审要素</th>
                  <th>评审内容</th>
                </tr>
              </thead>
              <tbody>
                {pkg['技术评分规则'].map((item, index) => (
                  <tr key={index}>
                    <td>{item['项目']}</td>
                    <td>{item['评审要素']}</td>
                    <td>{item['评审内容']}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
      {pkg['专用资格要求'] ? (
        <details className="score-rules">
          <summary>专用资格要求</summary>
          <div className="table-wrap">
            <table className="data-table score-rules-table">
              <thead>
                <tr>
                  {Object.keys(pkg['专用资格要求']).map((key) => (
                    <th key={key}>{key}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  {Object.values(pkg['专用资格要求']).map((value, index) => (
                    <td key={index}>{value}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
      {pkg['评分权重'] ? (
        <details className="score-rules">
          <summary>评分构成（技术 / 商务 / 价格权重）</summary>
          <div className="table-wrap">
            <table className="data-table score-rules-table">
              <thead>
                <tr>
                  <th>技术</th>
                  <th>商务</th>
                  <th>价格</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{pkg['评分权重']['技术'] ?? '-'}</td>
                  <td>{pkg['评分权重']['商务'] ?? '-'}</td>
                  <td>{pkg['评分权重']['价格'] ?? '-'}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </div>
  );
}

export function Preview({ initialTaskId, source }: { initialTaskId?: string; source?: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState(initialTaskId ?? '');
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(false);
  const [packages, setPackages] = useState<PackageData | null>(null);
  const [selectedFile, setSelectedFile] = useState<PackageFile | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileLoading, setFileLoading] = useState(false);
  const [pdfUrl, setPdfUrl] = useState('');
  const [activeTab, setActiveTab] = useState<'packages' | 'keyinfo' | 'rules' | 'files'>('packages');

  useEffect(() => {
    void api.listTasks(undefined, source).then((result) => {
      setTasks(result.items);
      if (!taskId && result.items[0]) {
        setTaskId(result.items[0].id);
      }
    });
  }, [taskId, source]);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    void api.getTask(taskId).then(setTask).finally(() => setLoading(false));
    setPackages(null);
    void api.getPackages(taskId).then(setPackages).catch(() => setPackages(null));
  }, [taskId]);

  const fields = task?.extracted_data ?? {};
  const meta = fields._meta;
  const entries = Object.entries(KEY_FIELDS)
    .map(([key, label]) => ({ key, label, value: fields[key] }))
    .filter((entry) => {
      const value = entry.value;
      if (!value || typeof value !== 'object' || !('primary_value' in value)) return false;
      const text = Array.isArray(value.primary_value) ? value.primary_value.join('、') : String(value.primary_value ?? '');
      return text.trim() !== '' && !(text.length <= 80 && REFERENCE_RE.test(text));
    });

  const selectFile = async (file: PackageFile) => {
    if (!task) return;
    setSelectedFile(file);
    setFileLoading(true);
    setFileContent('');
    setPdfUrl('');
    try {
      const suffix = file.source_path?.toLowerCase().split('.').pop() ?? '';
      if (['pdf', 'docx', 'doc'].includes(suffix)) {
        const blob = await api.getPackageFilePreviewBlob(task.id, file.source_path ?? file.md_path);
        setPdfUrl(URL.createObjectURL(blob));
      } else {
        const result = await api.getPackageFile(task.id, file.md_path);
        setFileContent(result.content);
      }
    } catch {
      setFileContent('文件内容读取失败');
    } finally {
      setFileLoading(false);
    }
  };

  let subprojects: SubprojectItem[] = [];
  if (packages?.subprojects?.length) {
    subprojects = packages.subprojects;
  } else if (packages?.packages?.length) {
    subprojects = [
      {
        '分标名称': packages.project['分标名称'] || '未分组',
        '分标编号': packages.project['分标编号'] || '',
        '项目名称': packages.project['项目名称'] || '',
        '项目编号': packages.project['项目编号'] || '',
        source_dir: '未分组',
        packages: packages.packages,
      },
    ];
  }

  return (
    <div className="gb-workbench gb-preview-workbench">
      <section className="gb-command-bar">
        <div className="gb-command-actions">
          <label className="gb-field gb-task-select">
            <span>任务</span>
            <select value={taskId} onChange={(event) => setTaskId(event.target.value)}>
              <option value="">选择任务</option>
              {tasks.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.original_file_name} · {new Date(item.created_at).toLocaleString('zh-CN', { hour12: false })}
                </option>
              ))}
            </select>
          </label>
          {task && <StatusBadge status={task.status} />}
        </div>
      </section>

      {loading ? (
        <EmptyState icon={<Layers size={36} />} title="加载中" />
      ) : !task ? (
        <EmptyState icon={<FileText size={36} />} title="选择任务查看抽取结果" />
      ) : (
        <>
          <section className="gb-summary-strip">
            <div className="gb-summary-item">
              <span>行业</span>
              <strong>{task.industry || '-'}</strong>
            </div>
            <div className="gb-summary-item">
              <span>抽取服务</span>
              <strong>{meta?.provider ?? '-'}</strong>
            </div>
            <div className="gb-summary-item">
              <span>置信度分布</span>
              <strong>
                {meta ? `${meta.confidence_summary.high} 高 / ${meta.confidence_summary.medium} 中 / ${meta.confidence_summary.low} 低` : '-'}
              </strong>
            </div>
            <div className="gb-summary-item">
              <span>合规状态</span>
              {task.check_result ? <ResultBadge result={task.check_result.status} /> : <strong>-</strong>}
            </div>
          </section>

          <div className="gb-preview-tabs" role="tablist">
            <button
              type="button"
              className={`gb-preview-tab ${activeTab === 'packages' ? 'is-active' : ''}`}
              onClick={() => setActiveTab('packages')}
              role="tab"
              aria-selected={activeTab === 'packages'}
            >
              <Archive size={15} />
              标包预览
              {subprojects.length > 0 ? <em>{subprojects.reduce((sum, item) => sum + item.packages.length, 0)}</em> : null}
            </button>
            <button
              type="button"
              className={`gb-preview-tab ${activeTab === 'keyinfo' ? 'is-active' : ''}`}
              onClick={() => setActiveTab('keyinfo')}
              role="tab"
              aria-selected={activeTab === 'keyinfo'}
            >
              <FileText size={15} />
              招标关键信息
              {entries.length > 0 ? <em>{entries.length}</em> : null}
            </button>
            <button
              type="button"
              className={`gb-preview-tab ${activeTab === 'files' ? 'is-active' : ''}`}
              onClick={() => setActiveTab('files')}
              role="tab"
              aria-selected={activeTab === 'files'}
            >
              <Layers size={15} />
              文件清单
              {task.manifest ? <em>{task.manifest.files.length}</em> : null}
            </button>
          </div>

          {activeTab === 'packages' && (
            packages && subprojects.length > 0 ? (
              <section className="gb-browse-panel">
                <div className="gb-browse-head">
                  <div>
                    <span className="gb-kicker">标包与产品</span>
                    <h3>标包预览</h3>
                  </div>
                  <button className="gb-secondary-action" onClick={() => void api.parsePackages(task.id).then(setPackages)}>
                    <RefreshCw size={14} />
                    重新解析
                  </button>
                </div>
                <div className="gb-browse-grid">
                  <div className="gb-subproject-col">
                    <div className="gb-subproject-list">
                      {subprojects.map((subproject) => (
                        <section className="gb-subproject-card" key={subproject.source_dir}>
                          <div className="gb-subproject-head">
                            <span className="gb-subproject-icon"><Archive size={16} /></span>
                            <div>
                              <strong>{subproject['分标名称'] || subproject.source_dir}</strong>
                              <span>{subproject.source_dir}</span>
                            </div>
                            <span className="gb-pill">{subproject.packages.length} 个包</span>
                          </div>
                          <div className="gb-meta-list">
                            {(['项目名称', '项目编号', '招标编号', '分标名称', '分标编号', '包名称', '包号'] as const)
                              .map((label) => {
                                const value = subproject[label] || packages.project[label] || '';
                                return value ? (
                                  <div className="gb-meta-row" key={label}>
                                    <span>{label}</span>
                                    <strong>{value}</strong>
                                  </div>
                                ) : null;
                              })}
                          </div>
                          <div className="gb-package-list">
                            {subproject.packages.map((pkg) => (
                              <PackageCard
                                key={pkg.source_archive}
                                pkg={pkg}
                                task={task}
                                project={packages.project}
                                subprojectDir={subproject.source_dir || subproject['分标名称']}
                                selectedFile={selectedFile}
                                onSelectFile={(file) => void selectFile(file)}
                              />
                            ))}
                          </div>
                        </section>
                      ))}
                    </div>
                  </div>
                  <div className="gb-file-viewer">
                    <div className="gb-file-viewer-head">
                      <div>
                        <span className="gb-kicker">文件内容</span>
                        <strong>{selectedFile?.name ?? '技术规范书内容'}</strong>
                      </div>
                      {selectedFile?.source_path && (
                        <button
                          className="gb-secondary-action"
                          onClick={() => {
                            void api.getPackageFileBlob(task.id, selectedFile.source_path ?? '').then((blob) => {
                              window.open(URL.createObjectURL(blob), '_blank');
                            });
                          }}
                        >
                          打开原文件
                        </button>
                      )}
                    </div>
                    <div className="gb-file-viewer-body-wrap">
                      {fileLoading ? (
                        <div className="gb-file-viewer-body">加载中…</div>
                      ) : pdfUrl ? (
                        <iframe className="gb-pdf-reader" src={pdfUrl} title={selectedFile?.name ?? 'PDF 预览'} />
                      ) : fileContent ? (
                        <div className="gb-file-reader" dangerouslySetInnerHTML={{ __html: markdownToHtml(fileContent) }} />
                      ) : (
                        <div className="gb-file-viewer-body">
                          <strong>选择技术规范书</strong>
                          <span>从左侧标包中选择技术规范书后展示文件内容</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </section>
            ) : (
              <section className="gb-browse-panel">
                <div className="gb-empty-state">
                  <Layers size={30} />
                  <strong>暂无标包数据</strong>
                  <span>该任务未解析出标包与技术规范书</span>
                </div>
              </section>
            )
          )}

          {activeTab === 'keyinfo' && (
            entries.length > 0 ? (
              <section className="gb-extract-panel">
                <div className="gb-card-head">
                  <div>
                    <span className="gb-kicker">信息抽取</span>
                    <h3>招标关键信息</h3>
                  </div>
                </div>
                <div className="gb-key-list">
                  {entries.map(({ key, label, value }) => {
                    const item = value as { primary_value: string | number | string[] };
                    const qualification = key === 'qualifications' ? (value as FieldValue & { structured?: QualificationStructured }).structured : undefined;
                    if (qualification) {
                      return (
                        <div className="gb-key-row gb-qual-row" key={key}>
                          <span className="gb-key-label">资质要求</span>
                          <div className="gb-key-value">
                            <div className="gb-qual-section">
                              <strong>产品资质（专用资格要求）</strong>
                              <div className="table-wrap">
                                <table className="data-table gb-qual-table">
                                  <thead>
                                    <tr>
                                      {qualification.product_table.columns.map((column) => (
                                        <th key={column}>{column}</th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {qualification.product_table.rows.map((row, rowIndex) => (
                                      <tr key={rowIndex}>
                                        {row.map((cell, cellIndex) => (
                                          <td key={cellIndex}>
                                            {cell && cell !== '/' && cell !== '-' ? cell : cell === '' ? '' : '未要求'}
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                            {qualification.enterprise.length > 0 && (
                              <div className="gb-qual-section">
                                <strong>企业资质</strong>
                                {qualification.enterprise.map((part, index) => (
                                  <div className="gb-key-item" key={index}>
                                    <span className="gb-key-item-no">{index + 1}</span>
                                    <span>{part}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                            {qualification.bidder.length > 0 && (
                              <div className="gb-qual-section">
                                <strong>投标人资格要求</strong>
                                {qualification.bidder.map((part, index) => (
                                  <div className="gb-key-item" key={index}>
                                    <span className="gb-key-item-no">{index + 1}</span>
                                    <span>{part}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    }
                    const text = Array.isArray(item.primary_value) ? item.primary_value.join('、') : String(item.primary_value ?? '');
                    const rawItems = Array.isArray(item.primary_value) ? item.primary_value.map(String) : [];
                    const items = rawItems.length > 0 ? rawItems : splitKeyText(text);
                    return (
                      <div className="gb-key-row" key={key}>
                        <span className="gb-key-label">{label}</span>
                        <div className="gb-key-value">
                          {items.length > 1 ? (
                            items.map((part, index) => (
                              <div className="gb-key-item" key={index}>
                                <span className="gb-key-item-no">{index + 1}</span>
                                <span>{part}</span>
                              </div>
                            ))
                          ) : (
                            items[0]
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            ) : (
              <section className="gb-extract-panel">
                <div className="gb-empty-state">
                  <FileText size={30} />
                  <strong>暂无关键信息</strong>
                </div>
              </section>
            )
          )}

          {activeTab === 'files' && (
            task.manifest ? (
              <section className="gb-manifest-panel">
                <div className="gb-card-head">
                  <div>
                    <span className="gb-kicker">文件清单</span>
                    <h3>{task.manifest.files.length} 个文件</h3>
                  </div>
                </div>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>文件</th>
                        <th>类型</th>
                        <th>页数</th>
                        <th>状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {task.manifest.files.map((file) => (
                        <tr key={file.rel_path}>
                          <td>{file.rel_path}</td>
                          <td>{file.type}</td>
                          <td>{file.page_count}</td>
                          <td>{file.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : (
              <section className="gb-manifest-panel">
                <div className="gb-empty-state">
                  <Layers size={30} />
                  <strong>暂无文件清单</strong>
                </div>
              </section>
            )
          )}
        </>
      )}
    </div>
  );
}

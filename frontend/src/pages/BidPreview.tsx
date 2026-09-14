import { useEffect, useState } from 'react';
import { Archive, ClipboardList, Download, FileText, Layers, RefreshCw } from 'lucide-react';
import { api, downloadBid } from '../api';
import type { PackageData, PackageFile, PackageItem, SubprojectItem, Task } from '../types';
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
  project_location: '项目地点',
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
  project_location: '项目地点',
  quality_standard: '质量标准',
  payment_terms: '付款方式',
  warranty: '质保期/质保要求',
};

const REFERENCE_RE = /见投标人须知前附表|见招标公告|见招标文件|详见招标公告|详见招标文件|以招标文件为准|同投标文件递交截止时间|同投标截止时间/;

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
  const [generated, setGenerated] = useState<{ bid_file_path: string; product_count: number } | null>(null);
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
    <article className="gb-package-card">
      <div className="gb-package-head">
        <span className="gb-package-icon"><Archive size={17} /></span>
        <div className="gb-package-title">
          <strong>{pkg['包名称'] || pkg['包号']}</strong>
          <span>{pkg['包号'] || pkg.package_no} · {specs.length} 款产品</span>
        </div>
      </div>
      {project['项目名称'] ? <p className="gb-package-project">项目：{project['项目名称']}</p> : null}
      <div className="gb-select-products">
        <strong>选择投标产品</strong>
        <div>
          {specs.map((file) => (
            <label className="gb-check" key={file.md_path}>
              <input type="checkbox" checked={selected.includes(file.md_path)} onChange={() => toggle(file.md_path)} />
              <span>{file.name}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="gb-package-actions">
        <button className="gb-primary-action" onClick={() => void generate()} disabled={!selected.length || busy}>
          生成该包投标文件
        </button>
        {generated && (
          <button className="gb-secondary-action" onClick={() => void download()}>
            下载投标文件（{generated.product_count} 款产品）
          </button>
        )}
      </div>
      <div className="gb-spec-list">
        {specs.map((file) => (
          <button
            type="button"
            className={`gb-spec-item ${selectedFile?.md_path === file.md_path ? 'is-active' : ''}`}
            key={file.rel_path}
            onClick={() => onSelectFile(file)}
          >
            <FileText size={15} />
            <div>
              {file.tech_spec_code && <span className="gb-spec-code">技术规范编码：{file.tech_spec_code}</span>}
              <strong>{file.name}</strong>
              <span>{file.has_tech_params ? '技术规范书 · 含技术特性参数表' : '技术规范书'}</span>
              <p>{file.content_preview || '（无文本内容）'}</p>
            </div>
          </button>
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
    </article>
  );
}

export function BidPreview({ initialTaskId, source = 'workbench' }: { initialTaskId?: string; source?: string }) {
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
    setSelectedFile(null);
    setFileContent('');
    setPdfUrl('');
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

  useEffect(() => {
    if (!packages || selectedFile) return;
    for (const subproject of packages.subprojects ?? []) {
      for (const pkg of subproject.packages ?? []) {
        const spec = (pkg.files ?? []).find((file) => file.kind === 'tech_spec');
        if (spec) {
          void selectFile(spec);
          return;
        }
      }
    }
  }, [packages, selectedFile]);

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

  const scoreRules: Array<{ 项目: string; 评审要素: string; 评审内容: string }> = [];
  const seenRules = new Set<string>();
  for (const subproject of subprojects) {
    for (const pkg of subproject.packages) {
      for (const item of pkg['技术评分规则'] || []) {
        const key = JSON.stringify(item);
        if (!seenRules.has(key)) {
          seenRules.add(key);
          scoreRules.push(item);
        }
      }
    }
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
          {task?.status === 'completed' && (
            <button className="gb-primary-action" onClick={() => void downloadBid(task.id)}>
              <Download size={15} />
              下载 DOCX
            </button>
          )}
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
              className={`gb-preview-tab ${activeTab === 'rules' ? 'is-active' : ''}`}
              onClick={() => setActiveTab('rules')}
              role="tab"
              aria-selected={activeTab === 'rules'}
            >
              <ClipboardList size={15} />
              技术评分规则
              {scoreRules.length > 0 ? <em>{scoreRules.length}</em> : null}
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
                    <div className="gb-spec-list">
                      {subprojects.flatMap((subproject) =>
                        subproject.packages.flatMap((pkg) =>
                          (pkg.files || [])
                            .filter((file) => file.kind === 'tech_spec')
                            .map((file) => (
                              <button
                                type="button"
                                className={`gb-spec-item ${selectedFile?.md_path === file.md_path ? 'is-active' : ''}`}
                                key={file.md_path}
                                onClick={() => void selectFile(file)}
                              >
                                <FileText size={15} />
                                <div>
                                  {file.tech_spec_code ? <span className="gb-spec-code">技术规范编码：{file.tech_spec_code}</span> : null}
                                  <strong>{file.name}</strong>
                                  <span>技术规范书{file.has_tech_params ? ' · 含技术特性参数表' : ''}</span>
                                  <p>{file.content_preview || '（无文本内容）'}</p>
                                </div>
                              </button>
                            )),
                        ),
                      )}
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
                    const text = Array.isArray(item.primary_value) ? item.primary_value.join('、') : String(item.primary_value ?? '');
                    const items = splitKeyText(text);
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

          {activeTab === 'rules' && (
            scoreRules.length > 0 ? (
              <section className="gb-extract-panel">
                <div className="gb-card-head">
                  <div>
                    <span className="gb-kicker">评审规则</span>
                    <h3>技术评分规则（{scoreRules.length} 条）</h3>
                  </div>
                </div>
                <div className="table-wrap">
                  <table className="gb-rule-table">
                    <thead>
                      <tr>
                        <th>项目</th>
                        <th>评审要素</th>
                        <th>评审内容</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scoreRules.map((item, index) => (
                        <tr key={index}>
                          <td>{item['项目']}</td>
                          <td>{item['评审要素']}</td>
                          <td>{item['评审内容']}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : (
              <section className="gb-extract-panel">
                <div className="gb-empty-state">
                  <ClipboardList size={30} />
                  <strong>暂无技术评分规则</strong>
                  <span>当前任务未解析出技术评分规则</span>
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

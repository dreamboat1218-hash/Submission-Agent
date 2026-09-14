import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, CloudUpload, Download, FileText, Play, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react';
import { api, downloadBid } from '../api';
import { useTaskProgress } from '../hooks/useTaskProgress';
import type { Task } from '../types';
import { StatusBadge } from '../components/StatusBadge';

const STAGES = [
  { key: 'preprocess', label: '文件预处理' },
  { key: 'extract', label: '信息抽取' },
  { key: 'generate', label: '标书生成' },
  { key: 'check', label: '合规检查' },
];

function fileBadge(name: string): string {
  const ext = name.split('.').pop() || 'FILE';
  return ext.length <= 5 ? ext.toUpperCase() : 'FILE';
}

export function Workbench({ onOpenPreview }: { onOpenPreview: (taskId: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState('fast');
  const [useKb, setUseKb] = useState(true);
  const [withCheck, setWithCheck] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const progress = useTaskProgress(task?.status === 'processing' || task?.status === 'queued' ? task.id : null);
  const [dragActive, setDragActive] = useState(false);

  const refresh = useCallback(async (taskId: string) => {
    try {
      const latest = await api.getTask(taskId);
      setTask(latest);
      return latest;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!task || !['queued', 'processing'].includes(task.status)) return;
    const timer = window.setInterval(() => {
      void refresh(task.id);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [task, refresh]);

  const upload = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError('');
    try {
      const created = await api.upload(file, { autoRun: true, mode, useKb, withCheck, source: 'workbench' });
      setTask(created);
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败');
    } finally {
      setBusy(false);
    }
  };

  const currentProgress = progress?.progress ?? task?.progress ?? 0;
  const stageIndex = STAGES.findIndex((stage) => stage.key === task?.current_stage);
  const meta = task?.extracted_data?._meta;

  return (
    <div className="gb-workbench gb-dashboard">
      <section className="gb-upload-board">
        <div className="gb-board-title">
          <div>
            <span className="gb-kicker">国网投标专项 · 工作台</span>
            <h2>选择标书</h2>
            <p>上传招标文件压缩包，自动完成解析、标包识别与投标文件生成</p>
          </div>
          <span className="gb-step-pill">STEP 01</span>
        </div>

        <div className="gb-upload-stack">
          <article
            className={`gb-upload-row${dragActive ? ' is-drag-over' : ''}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragActive(false);
              if (event.dataTransfer.files[0]) setFile(event.dataTransfer.files[0]);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              className="gb-hidden-input"
              onChange={(event) => {
                if (event.target.files?.[0]) setFile(event.target.files[0]);
              }}
            />
            <div className="gb-upload-label">
              <span>01</span>
              <strong>招标文件</strong>
              <small>必选 · zip / rar / 7z / tar.gz / pdf / docx</small>
            </div>
            <div className="gb-upload-content">
              {file ? (
                <div className="gb-file-pill">
                  <span className="gb-file-icon">{fileBadge(file.name)}</span>
                  <div className="gb-file-info">
                    <strong>{file.name}</strong>
                    <span>{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setFile(null);
                      if (inputRef.current) inputRef.current.value = '';
                    }}
                  >
                    移除
                  </button>
                </div>
              ) : (
                <button type="button" className="gb-upload-empty" onClick={() => inputRef.current?.click()}>
                  <strong>等待招标文件</strong>
                  <span>支持多层嵌套压缩包，可拖拽或点击选择</span>
                  <em>选择招标文件</em>
                </button>
              )}
            </div>
            <div className="gb-upload-actions">
              <label className="gb-field">
                <span>抽取模式</span>
                <select value={mode} onChange={(event) => setMode(event.target.value)}>
                  <option value="fast">快速模式</option>
                  <option value="precise">精准模式</option>
                </select>
              </label>
              <label className="gb-switch">
                <input type="checkbox" checked={useKb} onChange={(event) => setUseKb(event.target.checked)} />
                <span>知识库增强</span>
              </label>
              <label className="gb-switch">
                <input type="checkbox" checked={withCheck} onChange={(event) => setWithCheck(event.target.checked)} />
                <span>合规检查</span>
              </label>
              <button className="gb-primary-action" onClick={() => void upload()} disabled={!file || busy}>
                <Play size={15} />
                {busy ? '处理中…' : '开始处理'}
              </button>
            </div>
          </article>
        </div>
        {error && <div className="gb-error">{error}</div>}
      </section>

      <section className="gb-progress-card">
        <div className="gb-card-head">
          <div>
            <span className="gb-kicker">处理进度</span>
            <h3>{task ? task.original_file_name : '等待上传'}</h3>
          </div>
          {task && <StatusBadge status={task.status} />}
        </div>
        {!task ? (
          <div className="gb-empty-state">
            <CloudUpload size={34} />
            <strong>暂无任务</strong>
            <span>上传后自动完成解析、生成与检查</span>
          </div>
        ) : (
          <>
            <div className="gb-task-line">
              <span className="gb-file-icon gb-file-icon-sm">{fileBadge(task.original_file_name)}</span>
              <div>
                <strong>{task.original_file_name}</strong>
                <span>{task.industry || '行业待识别'}</span>
              </div>
            </div>
            <div className="gb-progress-track">
              <div className="gb-progress-fill" style={{ width: `${currentProgress}%` }} />
            </div>
            <div className="gb-progress-meta">
              <strong>{Math.round(currentProgress)}%</strong>
              <span>{progress?.message ?? task.message}</span>
            </div>
            <div className="gb-stepper">
              {STAGES.map((stage, index) => (
                <div
                  key={stage.key}
                  className={`gb-step ${index < stageIndex ? 'is-done' : ''} ${index === stageIndex ? 'is-current' : ''}`}
                >
                  <span className="gb-step-dot">{index < stageIndex ? <CheckCircle2 size={15} /> : index + 1}</span>
                  <span>{stage.label}</span>
                </div>
              ))}
            </div>
            <div className="gb-metric-row">
              <div className="gb-metric">
                <span>文件数</span>
                <strong>{task.file_count}</strong>
              </div>
              <div className="gb-metric">
                <span>字段数</span>
                <strong>{meta?.field_count ?? '-'}</strong>
              </div>
              <div className="gb-metric">
                <span>合规状态</span>
                <strong>{task.check_result?.status ?? '-'}</strong>
              </div>
            </div>
            {task.status === 'completed' && (
              <div className="gb-action-row">
                <button className="gb-secondary-action" onClick={() => onOpenPreview(task.id)}>
                  <Sparkles size={15} />
                  查看结果
                </button>
                <button className="gb-primary-action" onClick={() => void downloadBid(task.id)}>
                  <Download size={15} />
                  下载标书
                </button>
              </div>
            )}
            {task.status === 'failed' && <div className="gb-error">{task.error_message}</div>}
          </>
        )}
      </section>

      <section className="gb-stats-strip">
        <div className="gb-stat-card">
          <span className="gb-stat-icon"><ShieldCheck size={19} /></span>
          <div>
            <strong>{task?.check_result?.summary?.pass ?? 0}</strong>
            <span>检查通过</span>
          </div>
        </div>
        <div className="gb-stat-card">
          <span className="gb-stat-icon"><RefreshCw size={19} /></span>
          <div>
            <strong>{meta?.provider === 'tender-extract' ? 'tender-extract' : '规则引擎'}</strong>
            <span>抽取服务</span>
          </div>
        </div>
        <div className="gb-stat-card">
          <span className="gb-stat-icon"><FileText size={19} /></span>
          <div>
            <strong>{task?.file_count ?? 0}</strong>
            <span>解析文件数</span>
          </div>
        </div>
      </section>
    </div>
  );
}

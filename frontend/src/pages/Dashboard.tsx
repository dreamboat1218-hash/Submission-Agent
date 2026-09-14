import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, CloudUpload, Download, FileText, FileUp, Play, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react';
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

export function Dashboard({ onOpenPreview }: { onOpenPreview: (taskId: string) => void }) {
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
      const created = await api.upload(file, { autoRun: true, mode, useKb, withCheck, source: 'bid_special' });
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
    <div className="dashboard-grid">
      <section className="panel upload-panel">
        <div className="panel-header">
          <h2>招标文件</h2>
          <span className="panel-hint">zip / rar / 7z / tar.gz / pdf / docx</span>
        </div>
        <label
          className={`dropzone ${dragActive ? 'dropzone-active' : ''}`}
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
            onChange={(event) => {
              if (event.target.files?.[0]) setFile(event.target.files[0]);
            }}
          />
          <FileUp size={34} />
          <strong>{file ? file.name : '选择或拖入招标文件'}</strong>
          <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : '支持多层嵌套压缩包'}</span>
        </label>
        <div className="form-row">
          <label className="field field-inline">
            <span>抽取模式</span>
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="fast">快速模式</option>
              <option value="precise">精准模式</option>
            </select>
          </label>
          <label className="switch-row">
            <input type="checkbox" checked={useKb} onChange={(event) => setUseKb(event.target.checked)} />
            <span>知识库增强</span>
          </label>
          <label className="switch-row">
            <input type="checkbox" checked={withCheck} onChange={(event) => setWithCheck(event.target.checked)} />
            <span>合规检查</span>
          </label>
        </div>
        <button className="button button-primary button-block" onClick={upload} disabled={!file || busy}>
          <Play size={16} />
          {busy ? '处理中…' : '开始处理'}
        </button>
        {error && <div className="form-error">{error}</div>}
      </section>

      <section className="panel task-panel">
        <div className="panel-header">
          <h2>处理进度</h2>
          {task && <StatusBadge status={task.status} />}
        </div>
        {!task ? (
          <div className="empty-state empty-state-large">
            <CloudUpload size={42} />
            <p>上传后自动完成解析、生成与检查</p>
          </div>
        ) : (
          <>
            <div className="task-title">
              <FileText size={18} />
              <div>
                <strong>{task.original_file_name}</strong>
                <span>{task.industry || '行业待识别'}</span>
              </div>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${currentProgress}%` }} />
            </div>
            <div className="progress-meta">
              <span>{Math.round(currentProgress)}%</span>
              <span>{progress?.message ?? task.message}</span>
            </div>
            <div className="stepper">
              {STAGES.map((stage, index) => (
                <div key={stage.key} className={`step ${index < stageIndex ? 'step-done' : ''} ${index === stageIndex ? 'step-current' : ''}`}>
                  <span className="step-dot">{index < stageIndex ? <CheckCircle2 size={15} /> : index + 1}</span>
                  <span>{stage.label}</span>
                </div>
              ))}
            </div>
            <div className="metric-row">
              <div className="metric">
                <span>文件数</span>
                <strong>{task.file_count}</strong>
              </div>
              <div className="metric">
                <span>字段数</span>
                <strong>{meta?.field_count ?? '-'}</strong>
              </div>
              <div className="metric">
                <span>合规状态</span>
                <strong>{task.check_result?.status ?? '-'}</strong>
              </div>
            </div>
            {task.status === 'completed' && (
              <div className="action-row">
                <button className="button button-secondary" onClick={() => onOpenPreview(task.id)}>
                  <Sparkles size={16} />
                  查看结果
                </button>
                <button className="button button-secondary" onClick={() => void downloadBid(task.id)}>
                  <Download size={16} />
                  下载标书
                </button>
              </div>
            )}
            {task.status === 'failed' && <div className="form-error">{task.error_message}</div>}
          </>
        )}
      </section>

      <section className="panel stats-panel">
        <div className="stat-block">
          <ShieldCheck size={20} />
          <div>
            <strong>{task?.check_result?.summary?.pass ?? 0}</strong>
            <span>检查通过</span>
          </div>
        </div>
        <div className="stat-block">
          <RefreshCw size={20} />
          <div>
            <strong>{meta?.provider === 'tender-extract' ? 'tender-extract' : '规则引擎'}</strong>
            <span>抽取服务</span>
          </div>
        </div>
      </section>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { ClipboardCheck, ShieldAlert, ShieldCheck } from 'lucide-react';
import { api } from '../api';
import type { Task } from '../types';
import { EmptyState, ResultBadge } from '../components/StatusBadge';

export function Compliance() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState('');
  const [task, setTask] = useState<Task | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api.listTasks().then((result) => {
      setTasks(result.items);
      const first = result.items.find((item) => item.bid_file_path);
      if (first) setTaskId(first.id);
    });
  }, []);

  useEffect(() => {
    if (!taskId) return;
    void api.getTask(taskId).then(setTask);
  }, [taskId]);

  const runCheck = async () => {
    if (!taskId || busy) return;
    setBusy(true);
    try {
      await api.check(taskId);
      const deadline = Date.now() + 30000;
      const poll = window.setInterval(async () => {
        const latest = await api.getTask(taskId);
        setTask(latest);
        if (latest.check_result || latest.status === 'failed' || Date.now() > deadline) {
          window.clearInterval(poll);
          setBusy(false);
        }
      }, 1500);
    } catch {
      setBusy(false);
    }
  };

  const report = task?.check_result;

  return (
    <div className="compliance-layout">
      <section className="panel compliance-toolbar">
        <label className="field field-grow">
          <span>任务</span>
          <select value={taskId} onChange={(event) => setTaskId(event.target.value)}>
            <option value="">选择已生成标书的任务</option>
            {tasks
              .filter((item) => item.bid_file_path)
              .map((item) => (
                <option key={item.id} value={item.id}>{item.original_file_name}</option>
              ))}
          </select>
        </label>
        <button className="button button-primary" onClick={() => void runCheck()} disabled={!taskId || busy}>
          <ClipboardCheck size={16} />
          {busy ? '检查中…' : '运行检查'}
        </button>
      </section>

      {!report ? (
        <EmptyState icon={<ShieldCheck size={36} />} title="运行检查后展示废标项报告" />
      ) : (
        <>
          <section className="panel compliance-summary">
            <div className="summary-item">
              <span>总体结论</span>
              <ResultBadge result={report.status} />
            </div>
            <div className="summary-item">
              <span>检查时间</span>
              <strong>{new Date(report.check_time).toLocaleString('zh-CN', { hour12: false })}</strong>
            </div>
            <div className="summary-item">
              <span>通过</span>
              <strong className="text-pass">{report.summary.pass}</strong>
            </div>
            <div className="summary-item">
              <span>警告</span>
              <strong className="text-warn">{report.summary.warn}</strong>
            </div>
            <div className="summary-item">
              <span>失败</span>
              <strong className="text-fail">{report.summary.fail}</strong>
            </div>
          </section>
          <section className="panel">
            <div className="panel-header">
              <h2>检查明细</h2>
            </div>
            <div className="check-list">
              {report.items.map((item) => (
                <div className={`check-item check-item-${item.result.toLowerCase()}`} key={item.name}>
                  <span className="check-icon">{item.result === 'PASS' ? <ShieldCheck size={17} /> : <ShieldAlert size={17} />}</span>
                  <div className="check-main">
                    <strong>{item.name}</strong>
                    <p>{item.detail}</p>
                    {item.suggestion && <span className="check-suggestion">{item.suggestion}</span>}
                  </div>
                  <ResultBadge result={item.result} />
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

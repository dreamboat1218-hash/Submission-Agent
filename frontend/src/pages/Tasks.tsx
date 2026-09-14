import { useEffect, useState } from 'react';
import { Eye, RefreshCw, Trash2 } from 'lucide-react';
import { api } from '../api';
import type { Task } from '../types';
import { EmptyState, StatusBadge } from '../components/StatusBadge';

export function Tasks({ onOpenPreview, source }: { onOpenPreview: (taskId: string) => void; source?: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.listTasks(undefined, source);
      setTasks(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const remove = async (taskId: string) => {
    await api.deleteTask(taskId);
    await load();
  };

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>任务列表</h2>
        <button className="button button-ghost" onClick={() => void load()}>
          <RefreshCw size={15} />
          刷新
        </button>
      </div>
      {error && <div className="form-error">{error}</div>}
      {loading ? (
        <EmptyState icon={<RefreshCw size={34} />} title="加载中" />
      ) : tasks.length === 0 ? (
        <EmptyState icon={<Eye size={34} />} title="暂无任务" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>文件</th>
                <th>状态</th>
                <th>行业</th>
                <th>进度</th>
                <th>文件数</th>
                <th>更新时间</th>
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td>
                    <strong className="cell-main">{task.original_file_name}</strong>
                    <span className="cell-sub">{task.mode}</span>
                  </td>
                  <td><StatusBadge status={task.status} /></td>
                  <td>{task.industry || '-'}</td>
                  <td>
                    <div className="mini-progress">
                      <span style={{ width: `${task.progress}%` }} />
                    </div>
                    <span className="cell-sub">{Math.round(task.progress)}%</span>
                  </td>
                  <td>{task.file_count}</td>
                  <td>{new Date(task.updated_at).toLocaleString('zh-CN', { hour12: false })}</td>
                  <td className="col-actions">
                    <button className="icon-button" title="查看" onClick={() => onOpenPreview(task.id)}><Eye size={15} /></button>
                    <button className="icon-button icon-button-danger" title="删除" onClick={() => void remove(task.id)}><Trash2 size={15} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

import type { ReactNode } from 'react';

const STATUS_LABELS: Record<string, string> = {
  created: '已创建',
  queued: '排队中',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABELS[status] ?? status}</span>;
}

export function ResultBadge({ result }: { result: string }) {
  return <span className={`badge badge-result-${result.toLowerCase()}`}>{result}</span>;
}

export function ConfidenceBadge({ confidence }: { confidence: number }) {
  const tone = confidence >= 0.9 ? 'high' : confidence >= 0.7 ? 'medium' : 'low';
  return <span className={`badge badge-confidence badge-confidence-${tone}`}>{Math.round(confidence * 100)}%</span>;
}

export function FieldValue({ value }: { value: string | number | string[] | Record<string, unknown> }) {
  if (Array.isArray(value)) {
    return (
      <ul className="value-list">
        {value.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === 'object' && value !== null) {
    return <span>{JSON.stringify(value)}</span>;
  }
  return <span>{String(value)}</span>;
}

export function EmptyState({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="empty-state">
      {icon}
      <p>{title}</p>
    </div>
  );
}

import { useState } from 'react';
import { FileSearch, FileUp, Settings2, Workflow } from 'lucide-react';
import { Dashboard } from './Dashboard';
import { Preview } from './Preview';
import { Tasks } from './Tasks';
import { BidKnowledgeRules } from './BidKnowledgeRules';

type BidTab = 'upload' | 'tasks' | 'preview' | 'rules';

export function BidSpecial({
  initialTaskId,
  onSelectTask,
}: {
  initialTaskId?: string;
  onSelectTask: (taskId: string) => void;
}) {
  const [tab, setTab] = useState<BidTab>('upload');

  const openPreview = (taskId: string) => {
    setTab('preview');
    onSelectTask(taskId);
  };

  return (
    <div className="bid-special">
      <div className="bid-tabs" role="tablist">
        <button
          className={`bid-tab ${tab === 'upload' ? 'bid-tab-active' : ''}`}
          onClick={() => setTab('upload')}
          role="tab"
          aria-selected={tab === 'upload'}
        >
          <FileUp size={16} />
          上传标书
        </button>
        <button
          className={`bid-tab ${tab === 'preview' ? 'bid-tab-active' : ''}`}
          onClick={() => setTab('preview')}
          role="tab"
          aria-selected={tab === 'preview'}
        >
          <FileSearch size={16} />
          标书预览
        </button>
        <button
          className={`bid-tab ${tab === 'tasks' ? 'bid-tab-active' : ''}`}
          onClick={() => setTab('tasks')}
          role="tab"
          aria-selected={tab === 'tasks'}
        >
          <Workflow size={16} />
          任务中心
        </button>
        <button
          className={`bid-tab ${tab === 'rules' ? 'bid-tab-active' : ''}`}
          onClick={() => setTab('rules')}
          role="tab"
          aria-selected={tab === 'rules'}
        >
          <Settings2 size={16} />
          知识映射规则
        </button>
      </div>
      {tab === 'upload' ? (
        <div className="bid-upload">
          <Dashboard onOpenPreview={openPreview} />
        </div>
      ) : tab === 'tasks' ? (
        <Tasks source="bid_special" onOpenPreview={openPreview} />
      ) : tab === 'preview' ? (
        <Preview initialTaskId={initialTaskId} source="bid_special" />
      ) : (
        <BidKnowledgeRules />
      )}
    </div>
  );
}

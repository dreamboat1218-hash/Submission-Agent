import { useEffect, useState } from 'react';
import { Archive, BookOpen, ClipboardCheck, FileSearch, Gauge, LogOut, Settings as SettingsIcon, Workflow } from 'lucide-react';
import { api, getToken, setToken } from './api';
import { Login } from './components/Login';
import { Tasks } from './pages/Tasks';
import { Workbench } from './pages/Workbench';
import { BidPreview } from './pages/BidPreview';
import { Knowledge } from './pages/Knowledge';
import { Compliance } from './pages/Compliance';
import { BidSpecial } from './pages/BidSpecial';
import { Settings } from './pages/Settings';
import type { User } from './types';

type View = 'dashboard' | 'tasks' | 'preview' | 'knowledge' | 'compliance' | 'bid' | 'settings';

const NAV: Array<{ key: View; label: string; icon: typeof Gauge }> = [
  { key: 'dashboard', label: '工作台', icon: Gauge },
  { key: 'tasks', label: '任务中心', icon: Workflow },
  { key: 'preview', label: '标书预览', icon: FileSearch },
  { key: 'knowledge', label: '知识库', icon: BookOpen },
  { key: 'compliance', label: '合规检查', icon: ClipboardCheck },
  { key: 'bid', label: '国网投标专项', icon: Archive },
  { key: 'settings', label: '系统设置', icon: SettingsIcon },
];

export default function App() {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<View>('dashboard');
  const [selectedTaskId, setSelectedTaskId] = useState('');

  useEffect(() => {
    if (!token) return;
    void api.me().then(setUser).catch(() => {
      setToken(null);
      setTokenState(null);
    });
  }, [token]);

  useEffect(() => {
    const handleUnauthorized = () => {
      setToken(null);
      setTokenState(null);
      setUser(null);
    };
    window.addEventListener('bid-agent:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('bid-agent:unauthorized', handleUnauthorized);
  }, []);

  if (!token) {
    return (
      <Login
        onLogin={() => {
          setTokenState(getToken());
          setView('dashboard');
        }}
      />
    );
  }

  const openPreview = (taskId: string) => {
    setSelectedTaskId(taskId);
    setView('preview');
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><Workflow size={20} /></span>
          <div>
            <strong>投标智能体</strong>
            <span>集成流水线</span>
          </div>
        </div>
        <nav className="nav">
          {NAV.map(({ key, label, icon: Icon }) => (
            <button key={key} className={`nav-item ${view === key ? 'nav-item-active' : ''}`} onClick={() => setView(key)}>
              <Icon size={17} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-user">
          <span className="avatar">{user?.username.slice(0, 1).toUpperCase()}</span>
          <div>
            <strong>{user?.username}</strong>
            <span>{user?.role}</span>
          </div>
          <button
            className="icon-button"
            title="退出"
            onClick={() => {
              setToken(null);
              setTokenState(null);
            }}
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <h1>{NAV.find((item) => item.key === view)?.label}</h1>
          <span className="topbar-meta">{user?.role} · {user?.username}</span>
        </header>
        <div className="content">
          {view === 'dashboard' && <Workbench onOpenPreview={openPreview} />}
          {view === 'tasks' && <Tasks source="workbench" onOpenPreview={openPreview} />}
          {view === 'preview' && <BidPreview initialTaskId={selectedTaskId} source="workbench" />}
          {view === 'knowledge' && <Knowledge />}
          {view === 'compliance' && <Compliance />}
          {view === 'bid' && <BidSpecial initialTaskId={selectedTaskId} onSelectTask={setSelectedTaskId} />}
          {view === 'settings' && <Settings />}
        </div>
      </main>
    </div>
  );
}

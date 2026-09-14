import { useState } from 'react';
import { KeyRound, LogIn } from 'lucide-react';
import { api, setToken } from '../api';

export function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin123');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const result = await api.login(username, password);
      setToken(result.token);
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-panel" onSubmit={submit}>
        <div className="login-brand">
          <span className="brand-mark"><KeyRound size={22} /></span>
          <h1>招投标智能体集成系统</h1>
          <p>上传招标文件 → 自动解析 → 智能生成投标书</p>
        </div>
        <label className="field">
          <span>用户名</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label className="field">
          <span>密码</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
        </label>
        {error && <div className="form-error">{error}</div>}
        <button className="button button-primary button-block" type="submit" disabled={loading}>
          <LogIn size={16} />
          {loading ? '登录中…' : '登录'}
        </button>
      </form>
    </div>
  );
}

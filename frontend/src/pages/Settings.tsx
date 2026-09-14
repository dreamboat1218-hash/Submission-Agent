import { useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, Cpu, Database, FolderOpen, Plus, Save, Server, Trash2 } from 'lucide-react';
import { api } from '../api';
import type { Health, SystemSettings } from '../types';

const TENDER_LLM_PROVIDERS = [
  { value: 'none', label: '不使用 LLM', model: '' },
  { value: 'siliconflow', label: '硅基流动 SiliconFlow', model: 'Qwen/Qwen2.5-7B-Instruct' },
  { value: 'deepseek', label: 'DeepSeek', model: 'deepseek-chat' },
  { value: 'openai', label: 'OpenAI', model: 'gpt-4o-mini' },
  { value: 'qwen', label: '阿里云通义千问', model: 'qwen-plus' },
  { value: 'moonshot', label: 'Moonshot / Kimi', model: 'moonshot-v1-auto' },
  { value: 'zhipu', label: '智谱 GLM', model: 'glm-4-flash' },
  { value: 'ollama', label: 'Ollama（本地）', model: 'qwen2.5:14b' },
  { value: 'openai_compat', label: '任意 OpenAI 兼容接口', model: 'gpt-4o-mini' },
];

interface LlmProviderConfig {
  provider: string;
  model: string;
  api_key: string;
  base_url: string;
}

export function Settings() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [tenderUrl, setTenderUrl] = useState('');
  const [tenderApiKey, setTenderApiKey] = useState('');
  const [tenderLlmProviders, setTenderLlmProviders] = useState<LlmProviderConfig[]>([]);
  const [biaoshuPath, setBiaoshuPath] = useState('');
  const [message, setMessage] = useState('');

  const load = async () => {
    const data = await api.settings();
    setSettings(data);
    setTenderUrl(data.tender_extract_url);
    setTenderApiKey(data.tender_extract_api_key ?? '');
    const providers = data.tender_llm_providers ?? [];
    if (providers.length > 0) {
      setTenderLlmProviders(providers.map((item) => ({
        provider: item.provider,
        model: item.model,
        api_key: item.api_key ?? '',
        base_url: item.base_url ?? '',
      })));
    } else if (data.tender_llm_provider && data.tender_llm_provider !== 'none') {
      setTenderLlmProviders([{
        provider: data.tender_llm_provider,
        model: data.tender_llm_model ?? '',
        api_key: data.tender_llm_api_key ?? '',
        base_url: data.tender_llm_base_url ?? '',
      }]);
    } else {
      setTenderLlmProviders([]);
    }
    setBiaoshuPath(data.biaoshu_skill_path);
  };

  useEffect(() => {
    void load();
    void api.health().then(setHealth);
  }, []);

  const saveTender = async () => {
    try {
      const saved = await api.updateSettings({
        tender_extract_url: tenderUrl,
        tender_extract_api_key: tenderApiKey,
        tender_llm_providers: tenderLlmProviders.map((item) => ({ ...item })),
      });
      setSettings(saved);
      setTenderApiKey(saved.tender_extract_api_key ?? '');
      setTenderLlmProviders((saved.tender_llm_providers ?? []).map((item) => ({
        provider: item.provider,
        model: item.model,
        api_key: item.api_key ?? '',
        base_url: item.base_url ?? '',
      })));
      setMessage('tender-extract 配置已保存，新任务会读取新地址');
      void api.health().then(setHealth);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'tender-extract 配置保存失败');
    }
  };

  const addLlmProvider = () => {
    setTenderLlmProviders((current) => [
      ...current,
      { provider: 'siliconflow', model: 'Qwen/Qwen2.5-7B-Instruct', api_key: '', base_url: '' },
    ]);
  };

  const updateLlmProvider = (index: number, field: keyof LlmProviderConfig, value: string) => {
    setTenderLlmProviders((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? { ...item, [field]: value } : item)),
    );
  };

  const removeLlmProvider = (index: number) => {
    setTenderLlmProviders((current) => current.filter((_, itemIndex) => itemIndex !== index));
  };

  const moveLlmProvider = (index: number, direction: -1 | 1) => {
    setTenderLlmProviders((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const saveBiaoshu = async () => {
    try {
      const saved = await api.updateSettings({ biaoshu_skill_path: biaoshuPath });
      setSettings(saved);
      setMessage('BiaoShu-SKILL 配置已保存，新任务会读取新路径');
      void api.health().then(setHealth);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'BiaoShu-SKILL 配置保存失败');
    }
  };

  return (
    <div className="settings-grid">
      <section className="panel">
        <div className="panel-header">
          <h2>服务状态</h2>
        </div>
        <div className="service-list">
          {health
            ? Object.entries(health.services).map(([name, status]) => (
                <div className="service-item" key={name}>
                  <Server size={17} />
                  <strong>{name}</strong>
                  <span className="service-status">{status}</span>
                </div>
              ))
            : '加载中'}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>tender-extract 配置</h2>
        </div>
        <div className="settings-config-body">
          <label className="field">
            <span>服务地址</span>
            <input
              value={tenderUrl}
              onChange={(event) => setTenderUrl(event.target.value)}
              placeholder="http://127.0.0.1:8000"
            />
          </label>
          <p className="form-note">示例：http://127.0.0.1:8000</p>
          <label className="field">
            <span>API Key（可选）</span>
            <input
              value={tenderApiKey}
              onChange={(event) => setTenderApiKey(event.target.value)}
              placeholder="留空表示清除；显示 ****** 表示已配置"
            />
          </label>
          <div className="settings-llm-head">
            <strong>LLM 优先级配置</strong>
            <button className="button button-secondary" onClick={addLlmProvider}>
              <Plus size={14} />
              新增 LLM
            </button>
          </div>
          {tenderLlmProviders.length === 0 && (
            <p className="form-note">当前未配置 LLM，tender-extract 将使用规则抽取。</p>
          )}
          {tenderLlmProviders.map((item, index) => {
            const selected = TENDER_LLM_PROVIDERS.find((provider) => provider.value === item.provider);
            return (
              <div className="settings-llm-card" key={index}>
                <div className="settings-llm-card-head">
                  <strong>优先级 {index + 1}</strong>
                  <div className="rule-actions">
                    <button className="icon-button" title="上移" onClick={() => moveLlmProvider(index, -1)}>
                      <ArrowUp size={14} />
                    </button>
                    <button className="icon-button" title="下移" onClick={() => moveLlmProvider(index, 1)}>
                      <ArrowDown size={14} />
                    </button>
                    <button className="icon-button icon-button-danger" title="删除" onClick={() => removeLlmProvider(index)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                <label className="field">
                  <span>LLM 提供方</span>
                  <select
                    className="rule-dir-select"
                    value={item.provider}
                    onChange={(event) => {
                      const provider = TENDER_LLM_PROVIDERS.find((entry) => entry.value === event.target.value);
                      updateLlmProvider(index, 'provider', event.target.value);
                      if (provider) updateLlmProvider(index, 'model', provider.model);
                    }}
                  >
                    {TENDER_LLM_PROVIDERS.map((provider) => (
                      <option key={provider.value} value={provider.value}>
                        {provider.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>模型名称</span>
                  <input
                    value={item.model}
                    onChange={(event) => updateLlmProvider(index, 'model', event.target.value)}
                    placeholder={selected?.model ?? '模型名称'}
                  />
                </label>
                <label className="field">
                  <span>API Key</span>
                  <input
                    value={item.api_key}
                    onChange={(event) => updateLlmProvider(index, 'api_key', event.target.value)}
                    placeholder="填对应厂商 API Key；Ollama 可留空"
                  />
                </label>
                <label className="field">
                  <span>Base URL（可选）</span>
                  <input
                    value={item.base_url}
                    onChange={(event) => updateLlmProvider(index, 'base_url', event.target.value)}
                    placeholder="如 https://api.siliconflow.cn/v1"
                  />
                </label>
              </div>
            );
          })}
          <p className="form-note">保存后需要重启 tender-extract 服务，LLM 配置才会生效；OCR 已默认开启。</p>
          <div className="settings-config-actions">
            <button className="button button-primary" onClick={() => void saveTender()}>
              <Save size={15} />
              保存 tender-extract
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>BiaoShu-SKILL 配置</h2>
        </div>
        <div className="settings-config-body">
          <label className="field">
            <span>SKILL 目录路径</span>
            <input
              value={biaoshuPath}
              onChange={(event) => setBiaoshuPath(event.target.value)}
              placeholder="/Users/yourname/BiaoShu-SKILL"
            />
          </label>
          <p className="form-note">示例：/Users/supeng/Desktop/BiaoShu-SKILL</p>
          <p className="form-note">该目录下需要存在 scripts/bid_writer_pipeline.py</p>
          <div className="settings-config-actions">
            <button className="button button-primary" onClick={() => void saveBiaoshu()}>
              <Save size={15} />
              保存 BiaoShu-SKILL
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>模型配置</h2>
        </div>
        <div className="settings-list">
          <div className="settings-row"><Cpu size={16} /><span>LLM 提供方</span><strong>{settings?.llm_provider ?? '-'}</strong></div>
          <div className="settings-row"><Database size={16} /><span>向量检索</span><strong>{settings?.use_vector_search ? '启用' : 'SQLite 关键词'}</strong></div>
          <div className="settings-row"><Server size={16} /><span>tender-extract</span><strong>{settings?.tender_extract_url ?? '-'}</strong></div>
          <div className="settings-row"><FolderOpen size={16} /><span>BiaoShu-SKILL</span><strong>{settings?.biaoshu_skill_path || '内置生成器'}</strong></div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>限制参数</h2>
        </div>
        <div className="settings-list">
          <div className="settings-row"><span>单文件上限</span><strong>{(settings?.max_file_size ?? 0) / 1024 / 1024} MB</strong></div>
          <div className="settings-row"><span>解压深度</span><strong>{settings?.max_extract_depth ?? '-'} 层</strong></div>
          <div className="settings-row"><span>单任务文件数</span><strong>{settings?.max_files_per_task ?? '-'} 个</strong></div>
          <div className="settings-row"><span>运行环境</span><strong>{settings?.system_env ?? '-'}</strong></div>
        </div>
      </section>

      {message && <div className="form-note settings-message">{message}</div>}
    </div>
  );
}

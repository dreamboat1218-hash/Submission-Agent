import { Fragment, useEffect, useState } from 'react';
import { Plus, RefreshCw, Save, Search, Settings2, Trash2 } from 'lucide-react';
import { api } from '../api';
import type { KbChapterRule, KbChapterRulePreview, KbFileTag } from '../types';

interface RuleDraft {
  keywords: string;
  directories: string[];
  tags: string;
  frontmatter: string;
  query: string;
  max_items: number;
}

export function BidKnowledgeRules() {
  const [ruleDrafts, setRuleDrafts] = useState<RuleDraft[]>([]);
  const [kbDirs, setKbDirs] = useState<string[]>([]);
  const [kbTags, setKbTags] = useState<KbFileTag[]>([]);
  const [previews, setPreviews] = useState<Record<number, KbChapterRulePreview>>({});
  const [message, setMessage] = useState('');

  const loadRules = async () => {
    try {
      const [rulesData, dirsData, tagsData] = await Promise.all([
        api.bidSpecialRules(),
        api.kbDirectories(),
        api.kbFilesTags(),
      ]);
      setKbDirs(dirsData.directories);
      setKbTags(tagsData.tags);
      setRuleDrafts(toDrafts(rulesData.rules));
      setMessage('');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '规则读取失败');
    }
  };

  useEffect(() => {
    void loadRules();
  }, []);

  const toDrafts = (rules: KbChapterRule[]): RuleDraft[] =>
    rules.map((rule) => ({
      keywords: rule.keywords.join('、'),
      directories: rule.directories,
      tags: rule.tags.join('、'),
      frontmatter: (rule.frontmatter ?? []).join('、'),
      query: rule.query,
      max_items: rule.max_items,
    }));

  const updateRule = (index: number, field: string, value: string | number | string[]) => {
    setRuleDrafts((current) => current.map((rule, i) => (i === index ? { ...rule, [field]: value } : rule)));
  };

  const addRule = () => {
    setRuleDrafts((current) => [...current, { keywords: '', directories: [], tags: '', frontmatter: '', query: '', max_items: 3 }]);
  };

  const removeRule = (index: number) => {
    setRuleDrafts((current) => current.filter((_, i) => i !== index));
  };

  const split = (value: string) => value.split(/[、,，;；]/).map((item) => item.trim()).filter(Boolean);

  const toRule = (draft: RuleDraft): KbChapterRule => ({
    keywords: split(draft.keywords),
    directories: draft.directories,
    tags: split(draft.tags),
    frontmatter: split(draft.frontmatter),
    query: draft.query.trim(),
    max_items: Math.max(1, Math.min(20, Number(draft.max_items) || 3)),
  });

  const saveRules = async () => {
    const rules = ruleDrafts.filter((rule) => rule.keywords.trim()).map(toRule);
    try {
      const saved = await api.bidSaveSpecialRules(rules);
      setRuleDrafts(toDrafts(saved.rules));
      setMessage('国网投标专用映射规则已保存');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '规则保存失败');
    }
  };

  const resetRules = async () => {
    try {
      const saved = await api.bidResetSpecialRules();
      setRuleDrafts(toDrafts(saved.rules));
      setMessage('已恢复国网投标专用固定默认规则');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '规则恢复失败');
    }
  };

  const previewRule = async (index: number) => {
    const draft = ruleDrafts[index];
    if (!draft?.keywords.trim()) return;
    try {
      const result = await api.bidPreviewSpecialRule(toRule(draft), split(draft.keywords)[0]);
      setPreviews((current) => ({ ...current, [index]: result }));
      setMessage('');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '试检索失败');
    }
  };

  return (
    <section className="panel rules-panel">
      <div className="panel-header">
        <h2>
          <Settings2 size={16} />
          国网投标专用知识映射规则
        </h2>
        <div className="obs-actions">
          <button className="button button-ghost" onClick={() => void resetRules()}>
            <RefreshCw size={15} />
            恢复默认
          </button>
          <button className="button button-secondary" onClick={addRule}>
            <Plus size={15} />
            新增映射
          </button>
          <button className="button button-primary" onClick={() => void saveRules()}>
            <Save size={15} />
            保存规则
          </button>
        </div>
      </div>
      <p className="panel-hint">
        国网投标专项生成包级投标文件时，按这些规则自动从知识库召回内容，填入“销售业绩、认证证书、许可证”等固定章节。
      </p>
      <p className="form-note">默认规则依赖知识库笔记的标签与 Frontmatter（doc_type、status、product），请在 Obsidian 笔记中补全后试检索。</p>
      <datalist id="bid-kb-tags-list">
        {kbTags.map((item) => (
          <option key={item.tag} value={item.tag} />
        ))}
      </datalist>
      <div className="rules-table-wrap">
        <table className="rules-table">
          <thead>
            <tr>
              <th className="col-keywords">章节关键词</th>
              <th className="col-dirs">知识库目录</th>
              <th className="col-tags">标签</th>
              <th className="col-frontmatter">Frontmatter 字段</th>
              <th className="col-query">检索词</th>
              <th className="col-count">条数</th>
              <th className="col-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            {ruleDrafts.map((rule, index) => (
              <Fragment key={index}>
                <tr>
                  <td>
                    <input
                      value={rule.keywords}
                      onChange={(event) => updateRule(index, 'keywords', event.target.value)}
                      placeholder="如：销售业绩、认证证书"
                    />
                  </td>
                  <td>
                    <select
                      className="rule-dir-select"
                      value={rule.directories[0] ?? ''}
                      onChange={(event) =>
                        updateRule(index, 'directories', event.target.value ? [event.target.value] : [])
                      }
                    >
                      <option value="">请选择知识库目录</option>
                      {kbDirs.map((dir) => (
                        <option key={dir} value={dir}>
                          {dir}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      list="bid-kb-tags-list"
                      value={rule.tags}
                      onChange={(event) => updateRule(index, 'tags', event.target.value)}
                      placeholder="如：业绩、认证证书"
                    />
                  </td>
                  <td>
                    <input
                      value={rule.frontmatter}
                      onChange={(event) => updateRule(index, 'frontmatter', event.target.value)}
                      placeholder="如：doc_type:企业资质、status:已中标"
                    />
                  </td>
                  <td>
                    <input
                      value={rule.query}
                      onChange={(event) => updateRule(index, 'query', event.target.value)}
                      placeholder="如：类似项目业绩 合同 验收"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={rule.max_items}
                      onChange={(event) => updateRule(index, 'max_items', Number(event.target.value))}
                    />
                  </td>
                  <td>
                    <div className="rule-actions">
                      <button className="button button-ghost" title="试检索" onClick={() => void previewRule(index)}>
                        <Search size={14} />
                      </button>
                      <button className="icon-button icon-button-danger" title="删除映射" onClick={() => removeRule(index)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
                {previews[index] && (
                  <tr className="rule-preview-row">
                    <td colSpan={7}>
                      <div className="rule-preview">
                        <div className="obs-engine">
                          试检索：{previews[index].title}（命中 {previews[index].items.length} 条）
                        </div>
                        {previews[index].items.length === 0 ? (
                          <div className="form-note">未命中知识笔记，请检查目录/标签/检索词</div>
                        ) : (
                          previews[index].items.map((item) => (
                            <div className="rule-preview-item" key={item.path}>
                              <strong>{item.path}</strong>
                              <span>{item.source ?? item.engine ?? '知识库'} · 相关度 {item.score.toFixed(2)}</span>
                              <p>{item.content?.slice(0, 140)}</p>
                            </div>
                          ))
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {message && <p className="form-note">{message}</p>}
    </section>
  );
}

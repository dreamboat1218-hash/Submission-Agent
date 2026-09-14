const CLAUSE_MARKER_RE = /\d+(?:\.\d+)+[.、．]|\d+[、．]|[（(]\d+[)）]|[①-⑩]/g;

/** 把长文本拆成 1、2、3 条目数组，便于列表化展示。 */
export function splitKeyText(text: string): string[] {
  const cleaned = text.replace(/\s+/g, ' ').trim();
  if (!cleaned) return [];

  const matches = Array.from(cleaned.matchAll(CLAUSE_MARKER_RE));
  if (matches.length > 0) {
    const parts: string[] = [];
    let cursor = 0;
    for (const match of matches) {
      const before = cleaned.slice(cursor, match.index ?? 0).trim();
      if (before) parts.push(before);
      cursor = (match.index ?? 0) + match[0].length;
    }
    const tail = cleaned.slice(cursor).trim();
    if (tail) parts.push(tail);
    const items = parts.map((part) => part.trim()).filter(Boolean);
    if (items.length >= 2) {
      return items;
    }
  }

  const sentences = cleaned
    .split(/(?<=[。；;])/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length >= 6);
  if (sentences.length >= 2) {
    const items: string[] = [];
    let current = '';
    for (const sentence of sentences) {
      if (current && (current + sentence).length > 60) {
        items.push(current);
        current = sentence;
      } else {
        current += sentence;
      }
    }
    if (current) items.push(current);
    return items;
  }

  return [cleaned];
}

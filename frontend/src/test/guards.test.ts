// Structural guards: the frontend is a client of the API and owns no screening logic.
import { describe, expect, it } from 'vitest';
import tokens from '../styles/tokens.css?raw';
import base from '../styles/base.css?raw';
import components from '../styles/components.css?raw';

const modules = import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const source = Object.entries(modules).filter(([path]) => !path.includes('/src/test/') && !/\.test\./.test(path));

describe('frontend owns no business logic', () => {
  it('finds the application sources', () => {
    expect(source.length).toBeGreaterThan(10);
  });

  it('only the API client calls fetch(), and nothing talks to GitHub or an LLM', () => {
    for (const [path, text] of source) {
      if (!path.endsWith('/api/client.ts')) expect(text, path).not.toMatch(/\bfetch\s*\(/);
      expect(text, path).not.toMatch(/api\.github\.com|openai|openrouter|anthropic|Authorization|Bearer|API_KEY|GITHUB_TOKEN/i);
    }
  });

  it('never sorts, re-ranks or reassigns result fields', () => {
    for (const [path, text] of source) {
      expect(text, path).not.toMatch(/\.sort\(|\.toSorted\(/);
      expect(text, path).not.toMatch(/\.(total_score|rank|eligible|score_breakdown|github_enrichment)\s*=(?!=)/);
    }
  });

  it('does no score arithmetic and no eligibility keyword matching', () => {
    for (const [path, text] of source) {
      expect(text, path).not.toMatch(/(ai_project_depth|python_backend|cloud_fullstack|engineering_depth|total_score)\s*[-+*/]\s*\w/);
      expect(text, path).not.toMatch(/\w\s*[-+*/]\s*\w*\.?(ai_project_depth|python_backend|cloud_fullstack|engineering_depth|total_score)\b/);
      expect(text, path).not.toMatch(/(includes|indexOf|match|test)\(\s*['"`/]\s*(python|langchain|langgraph|rag|llm|fastapi)/i);
    }
  });

  it('ships no demo candidate data: no email literals and nothing imported from src/test', () => {
    for (const [path, text] of source) {
      expect(text, path).not.toMatch(/[A-Za-z0-9._-]+@[A-Za-z0-9-]+\.[a-z]{2,}/);
      expect(text, path).not.toMatch(/from\s+['"][^'"]*\/test\//);
      expect(text, path).not.toMatch(/from\s+['"][^'"]*fixtures['"]|from\s+['"]vitest['"]/);
    }
  });

  it('does not store candidate data in the browser', () => {
    for (const [path, text] of source) expect(text, path).not.toMatch(/localStorage|sessionStorage|indexedDB/);
  });
});

describe('no information depends on hover (mobile / touch safe)', () => {
  it('hover rules only change colours, never visibility or layout', () => {
    const allowed = new Set(['background', 'background-color', 'color', 'border-color', 'box-shadow']);
    const css = [tokens, base, components].join('\n');
    const rules = [...css.matchAll(/([^{}]+):hover[^{}]*\{([^}]*)\}/g)];
    expect(rules.length).toBeGreaterThan(3);
    for (const [, selector, body] of rules) {
      const props = body.split(';').map((d) => d.split(':')[0].trim()).filter(Boolean);
      for (const prop of props) expect(allowed.has(prop), `${selector.trim()} :hover sets ${prop}`).toBe(true);
    }
  });

  it('respects reduced motion and has a mobile breakpoint', () => {
    expect(base).toMatch(/prefers-reduced-motion: reduce/);
    expect(components).toMatch(/max-width: 640px/);
  });
});

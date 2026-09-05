#!/usr/bin/env python3
"""Serve a dependency-free editable preview for an AI-generated card spec.

The browser edits the source spec, asks the local generator for a fresh Card
2.0 preview, and only writes files after the user clicks save. It deliberately
does not send anything to Feishu.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from auto_layout import build_auto_spec
from generate_card import build_card, compile_outputs, contains_placeholder, load_preset_registry, load_scene_registry, resolve_preset, resolve_scene, scene_contract_report
from runtime_profile import image_mode_config, supported_image_modes
from validate_card import validate


EDITOR_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>飞书卡片微调台</title>
<style>
:root { color-scheme: light; --ink:#172238; --muted:#667180; --paper:#f4f0e6; --line:#d8d5cd; --gold:#EACD76; --accent:#EACD76; --blue:#425066; --vermilion:#9D2933; --jade:#5AA4AE; --panel:#fffdf8; }
* { box-sizing:border-box; }
body { margin:0; min-height:100vh; background:radial-gradient(circle at 5% 0%,rgba(66,80,102,.22),transparent 32%),linear-gradient(135deg,#ebe7dd,#f8f5ed 50%,#e8ddd5); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif; }
button, input, textarea, select { font:inherit; }
button { cursor:pointer; }
.app { min-height:100vh; display:flex; flex-direction:column; }
.topbar { display:flex; justify-content:space-between; gap:16px; align-items:center; padding:16px 22px; background:linear-gradient(120deg,#0c1422,#263b58 58%,#955539); color:#fff; }
.topbar h1 { font-size:18px; margin:0 0 4px; letter-spacing:.02em; }
.topbar p { margin:0; color:#c9c6bf; font-size:12px; }
.toolbar { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
.toolbar button, .secondary { border:1px solid #5c5a55; border-radius:7px; background:#2a2926; color:#fff; padding:8px 12px; }
.toolbar .primary, .primary { border-color:var(--gold); background:var(--gold); color:#171717; font-weight:700; }
.workspace { flex:1; display:grid; grid-template-columns:minmax(360px, 470px) minmax(360px, 1fr); gap:14px; padding:14px; min-height:0; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; min-height:0; overflow:hidden; box-shadow:0 4px 14px rgba(28,25,20,.06); }
.editor-panel { display:flex; flex-direction:column; }
.tabs { display:flex; border-bottom:1px solid var(--line); background:#faf9f6; }
.tab { flex:1; border:0; border-bottom:2px solid transparent; padding:11px 10px; background:transparent; color:var(--muted); }
.tab.active { color:var(--ink); border-bottom-color:var(--gold); font-weight:700; }
.form-scroll { overflow:auto; padding:16px; }
.tab-pane { display:none; }
.tab-pane.active { display:block; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.field { display:flex; flex-direction:column; gap:5px; margin-bottom:12px; }
.field.full { grid-column:1 / -1; }
.field label, .field-title { font-size:12px; color:var(--muted); font-weight:700; }
.field input, .field textarea, .field select, .advanced-editor { width:100%; border:1px solid #d8d4cb; border-radius:7px; padding:8px 9px; background:#fff; color:var(--ink); }
.field textarea { min-height:66px; resize:vertical; line-height:1.5; }
.field input:focus, .field textarea:focus, .field select:focus, .advanced-editor:focus { outline:2px solid rgba(185,154,101,.28); border-color:var(--gold); }
.check-row { display:flex; gap:12px; flex-wrap:wrap; margin:3px 0 14px; }
.check-row label { font-size:12px; color:var(--muted); display:flex; gap:5px; align-items:center; }
.section-head { display:flex; justify-content:space-between; align-items:center; margin:20px 0 8px; padding-top:13px; border-top:1px solid #ebe8e1; }
.section-head h3 { margin:0; font-size:13px; }
.small-button { border:1px solid #d8d4cb; border-radius:6px; background:#fff; color:var(--ink); padding:5px 8px; font-size:12px; }
.repeat-item { border:1px solid #e3dfd7; border-radius:8px; padding:9px; margin:8px 0; background:#fcfbf9; }
.repeat-item .item-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:7px; color:var(--muted); font-size:11px; }
.repeat-item .remove { color:#9a3a2c; border:0; background:transparent; padding:0; }
.repeat-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.repeat-grid .full { grid-column:1 / -1; }
.repeat-grid input, .repeat-grid textarea, .repeat-grid select { width:100%; border:1px solid #dedad2; border-radius:6px; padding:7px; background:#fff; }
.repeat-grid textarea { min-height:54px; resize:vertical; }
.hint { color:var(--muted); font-size:11px; line-height:1.5; margin:5px 0 12px; }
.source-box { margin:14px; padding:12px; border:1px solid #ded9cf; border-radius:10px; background:#f7f3ea; }
.decision-box { margin:0 14px 14px; padding:12px; border:1px solid rgba(66,80,102,.2); border-radius:10px; background:linear-gradient(135deg,#f7f3ea,#eef2f6); }
.decision-box h3 { margin:0 0 8px; font-size:13px; }
.decision-grid { display:grid; grid-template-columns:1fr 1fr; gap:7px; font-size:11px; line-height:1.5; }
.decision-item { padding:7px; border-radius:6px; background:rgba(255,255,255,.72); }
.decision-item strong { display:block; color:#596273; }
.decision-reasons { margin:8px 0 0; padding-left:18px; color:var(--muted); font-size:11px; }
.source-actions { display:flex; justify-content:space-between; align-items:center; gap:10px; }
.source-actions h3 { margin:0; font-size:13px; }
.source-box textarea { width:100%; min-height:116px; margin-top:8px; resize:vertical; line-height:1.5; }
.advanced-editor { min-height:560px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; line-height:1.5; }
.advanced-actions { display:flex; gap:8px; margin:10px 0; }
.preview-panel { display:flex; flex-direction:column; min-width:0; }
.preview-head { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:12px 14px; border-bottom:1px solid var(--line); background:#faf9f6; }
.preview-head strong { font-size:13px; }
.preview-head span { color:var(--muted); font-size:11px; }
.preview-controls { display:flex; gap:7px; align-items:center; }
.preview-controls button { border:1px solid #d8d4cb; background:#fff; border-radius:6px; padding:5px 8px; font-size:11px; }
.preview-stage { flex:1; overflow:auto; padding:24px; display:flex; align-items:flex-start; justify-content:center; background:radial-gradient(circle at 0 0,rgba(234,205,118,.18),transparent 28%),linear-gradient(135deg,#172238,#425066 55%,#6f463b); }
.device { width:600px; max-width:100%; transition:width .18s ease; }
.device.mobile { width:360px; }
.device.desktop { width:720px; }
.feishu-card { overflow:hidden; border-radius:10px; background:#fffdf8; border:1px solid rgba(234,205,118,.62); box-shadow:0 14px 32px rgba(16,24,38,.28); }
.card-header { padding:15px 16px 13px; background:linear-gradient(135deg,#172238 0%,#425066 55%,#955539 100%); color:#fff; }
.card-header.black { background:#202020; color:#fff; }
.card-header.orange { background:#b76d25; color:#fff; }
.card-header.green { background:#5b846a; color:#fff; }
.card-header.yellow { background:#c39b32; color:#171717; }
.card-header.blue { background:#456da8; color:#fff; }
.card-header.red { background:#a84c42; color:#fff; }
.card-header.carmine { background:linear-gradient(135deg,#241827 0%,#9D2933 58%,#EACD76 100%); color:#fff; }
.card-header.indigo { background:linear-gradient(135deg,#172238 0%,#425066 55%,#955539 100%); color:#fff; }
.card-eyebrow { color:var(--gold); font-size:10px; letter-spacing:.08em; text-transform:uppercase; margin-bottom:5px; }
.card-header.black .card-eyebrow, .card-header.orange .card-eyebrow, .card-header.green .card-eyebrow, .card-header.blue .card-eyebrow, .card-header.red .card-eyebrow, .card-header.carmine .card-eyebrow, .card-header.indigo .card-eyebrow { color:#f3dfb4; }
.card-title { font-weight:760; font-size:19px; line-height:1.35; letter-spacing:-.015em; }
.card-subtitle { margin-top:3px; color:#6d6e6a; font-size:11px; }
.card-header.black .card-subtitle, .card-header.orange .card-subtitle, .card-header.green .card-subtitle, .card-header.blue .card-subtitle, .card-header.red .card-subtitle, .card-header.carmine .card-subtitle, .card-header.indigo .card-subtitle { color:#eee5d9; }
.header-tag { display:inline-block; margin-top:9px; border-radius:999px; padding:3px 7px; font-size:10px; background:rgba(255,255,255,.16); color:#fff; border:1px solid rgba(255,255,255,.28); }
.card-body { padding:13px 13px 19px; display:flex; flex-direction:column; gap:9px; background:#fbf8f0; }
.card-text { white-space:normal; line-height:1.62; font-size:13px; }
.card-text.heading { font-size:17px; font-weight:700; line-height:1.45; }
.card-text.heading-1 { font-size:22px; font-weight:760; line-height:1.35; }
.card-text.heading-2 { font-size:19px; font-weight:740; line-height:1.4; }
.card-text.heading-3 { font-size:16px; font-weight:720; line-height:1.45; }
.card-text.heading-4 { font-size:14px; font-weight:700; line-height:1.5; }
.card-text.notation { color:var(--muted); font-size:11px; letter-spacing:.01em; }
.card-text.accent { color:var(--accent); }
.card-text strong { font-weight:750; }
.card-text a { color:#2456a6; text-decoration:none; }
.card-eyebrow + .card-text { margin-top:2px; }
.card-columns { display:grid; gap:8px; }
.card-columns.bisect { grid-template-columns:repeat(2,minmax(0,1fr)); }
.card-columns.trisect { grid-template-columns:repeat(3,minmax(0,1fr)); }
.card-columns.stretch, .card-columns.none { grid-template-columns:minmax(0,1fr); }
.card-column { min-width:0; padding:9px; border-radius:8px; background:#f6f2e9; border:1px solid rgba(66,80,102,.08); display:flex; flex-direction:column; gap:4px; }
.card-hr { border:0; border-top:1px solid #e6e2d9; width:100%; margin:2px 0; }
.card-button { width:100%; border-radius:7px; padding:8px 10px; border:1px solid #cfcac0; background:#fff; color:#292824; font-weight:650; }
.card-button.primary_filled { border-color:var(--gold); background:var(--gold); color:#172238; box-shadow:0 4px 12px rgba(234,205,118,.25); }
.card-button.danger_filled { border-color:#ad4e43; background:#ad4e43; color:#fff; }
.image-placeholder { min-height:106px; border-radius:8px; background:linear-gradient(135deg,#f5f2e9,#dad4c5); display:flex; align-items:center; justify-content:center; text-align:center; color:#796d5d; font-size:11px; padding:12px; }
.image-preview-frame { overflow:hidden; border-radius:8px; background:#f5f2e9; border:1px solid rgba(66,80,102,.12); }
.image-preview-frame img { display:block; width:100%; height:auto; }
.image-combination { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px; }
.image-combination.triple, .image-combination.trisect { grid-template-columns:repeat(3,minmax(0,1fr)); }
.quote-box, .collapse-box, .table-box, .chart-box, .form-box { border-radius:8px; background:#f6f2e9; padding:11px; }
.quote-box { border-left:3px solid var(--gold); }
.collapse-box summary { cursor:pointer; font-size:12px; font-weight:700; color:#5d523e; }
.collapse-box[open] summary { margin-bottom:8px; }
.preview-table { width:100%; border-collapse:collapse; font-size:11px; }
.preview-table th, .preview-table td { text-align:left; padding:6px 5px; border-bottom:1px solid #dedad1; vertical-align:top; }
.preview-table th { color:#5f5547; background:#ebe7dd; }
.chart-box pre { white-space:pre-wrap; overflow:auto; max-height:180px; margin:7px 0 0; color:#6f6556; font-size:10px; }
.form-box input, .form-box select { width:100%; margin:4px 0 7px; border:1px solid #d8d4cb; border-radius:5px; padding:6px; background:#fff; }
.person-pill { display:inline-flex; align-items:center; gap:5px; border-radius:999px; padding:4px 7px; background:#ebe8e0; color:#5e5a52; font-size:11px; }
.status { padding:8px 14px; border-top:1px solid var(--line); color:var(--muted); font-size:11px; background:#faf9f6; }
.status.ok { color:#39704c; }
.status.error { color:#9a3a2c; }
@media (max-width: 900px) { .workspace { grid-template-columns:1fr; } .preview-panel { min-height:620px; } }
@media (max-width: 520px) { .topbar { align-items:flex-start; flex-direction:column; } .toolbar { justify-content:flex-start; } .workspace { padding:8px; } .grid, .repeat-grid { grid-template-columns:1fr; } .field.full, .repeat-grid .full { grid-column:auto; } .preview-stage { padding:12px 6px; } }
</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <div><h1>飞书卡片微调台</h1><p>AI 生成 → 人工微调 → 本地编译。不会自动发送。</p></div>
    <div class="toolbar">
      <button id="downloadSpec">下载 spec</button>
      <button id="downloadCard">下载 card</button>
      <button id="copyCardKit">复制 CardKit 导入命令</button>
      <button id="save" class="primary">保存并编译</button>
    </div>
  </header>
  <main class="workspace">
    <section class="panel editor-panel">
      <nav class="tabs"><button class="tab active" data-tab="quick">快捷微调</button><button class="tab" data-tab="advanced">高级 JSON</button></nav>
      <div id="quickPane" class="tab-pane active form-scroll">
        <div class="source-box">
          <div class="source-actions"><h3>原文入口 · 一键自动排版</h3><button id="autoLayout" class="primary" type="button">从原文生成</button></div>
          <textarea id="sourceText" placeholder="粘贴活动通知、培训安排、作品介绍或一段带链接的文本。系统会自动识别场景、日期、重点、Emoji 和 URL 按钮，并保留原文分析记录。"></textarea>
          <p class="hint">默认原文优先：只做结构化排版、日期可读化和明确图标替换；改写、补充和相似句合并需要人工确认。</p>
          <label class="inline-field">链接显示 <select id="link_mode"><option value="button">按钮承载（推荐）</option><option value="inline">正文保留 URL</option></select></label>
        </div>
        <aside id="decisionSummary" class="decision-box"><h3>AI 设计决策</h3><p class="hint">从原文生成后显示视觉原型、组件、图片、折叠与导航建议。</p></aside>
        <div class="grid">
          <div class="field"><label for="type">卡片类型</label><select id="type"><option>custom</option><option>timeline</option><option>training</option><option>story</option><option>submission</option><option>review</option><option>finalists</option><option>launch</option></select></div>
          <div class="field full"><label for="scene">活动环节 scene</label><select id="scene"><option value="">不指定环节</option></select><p id="sceneHint" class="hint">先选活动环节，系统会推荐版式配方和默认视觉风格。</p></div>
          <div class="field full"><label for="preset">视觉风格 preset</label><select id="preset"><option value="">自动：跟随 scene / 默认风格</option></select><p id="presetHint" class="hint">preset 负责色彩与视觉气质；scene 负责活动运营环节与内容配方。</p></div>
          <div class="field"><label for="theme">旧版主题快捷项</label><select id="theme"><option>oriental</option><option>ink</option><option>paper</option><option>warm</option><option>success</option><option>warning</option><option>danger</option><option>calm</option></select></div>
          <div class="field"><label for="width_mode">宽度</label><select id="width_mode"><option>default</option><option>compact</option><option>fill</option></select></div>
          <div class="field"><label for="date_label">日期标签</label><input id="date_label" /></div>
          <div class="field full"><label for="title">标题</label><textarea id="title"></textarea></div>
          <div class="field full"><label for="subtitle">副标题</label><input id="subtitle" /></div>
          <div class="field full"><label for="eyebrow">眉题 / 英文小标签</label><input id="eyebrow" /></div>
          <div class="field full"><label for="lead">开场重点</label><textarea id="lead"></textarea></div>
          <div class="field full"><label for="footer">页脚</label><textarea id="footer"></textarea></div>
        </div>
        <div class="check-row">
          <label><input type="checkbox" id="timeline_focus" /> 强化时间线</label>
          <label><input type="checkbox" id="timeline_first" /> 时间线置首屏</label>
          <label><input type="checkbox" id="collapse_supporting" /> 折叠补充信息</label>
          <label><input type="checkbox" id="emoji_normalize" /> 规范 Emoji 别名</label>
        </div>
        <div class="section-head"><h3>首图</h3></div>
        <div class="field"><label for="hero_img_key">img_key（可留空，生成 asset plan）</label><input id="hero_img_key" /></div>
        <div class="grid">
          <div class="field full"><label for="hero_alt">图片说明</label><input id="hero_alt" /></div>
          <div class="field full"><label for="hero_prompt">图片生成提示词</label><textarea id="hero_prompt"></textarea></div>
        </div>
        <div class="section-head"><h3>事实 / 指标</h3><button class="small-button" data-add="facts">+ 添加</button></div>
        <div id="factsList"></div>
        <div class="section-head"><h3>正文段落</h3><button class="small-button" data-add="sections">+ 添加</button></div>
        <div id="sectionsList"></div>
        <div class="section-head"><h3>时间线</h3><button class="small-button" data-add="timeline">+ 添加</button></div>
        <div id="timelineList"></div>
        <div class="section-head"><h3>按钮</h3><button class="small-button" data-add="buttons">+ 添加</button></div>
        <p class="hint">快捷编辑器优先展示 URL 按钮；已有 callback 的按钮不会被删除，但复杂回调请在高级 JSON 中修改。</p>
        <div id="buttonsList"></div>
        <div class="section-head"><h3>引用 / 理念</h3></div>
        <div id="quoteEditor"></div>
      </div>
      <div id="advancedPane" class="tab-pane form-scroll">
        <p class="hint">这里编辑的是可编译源 spec，不是最终 Card JSON。适合 blocks、table、chart、form、advanced_elements 等少见能力。修改后点击“应用 JSON”查看预览。</p>
        <textarea id="advancedEditor" class="advanced-editor" spellcheck="false"></textarea>
        <div class="advanced-actions"><button id="applyAdvanced" class="primary">应用 JSON</button><button id="formatAdvanced" class="secondary">格式化</button></div>
      </div>
    </section>
    <section class="panel preview-panel">
      <div class="preview-head"><div><strong>近似预览</strong><br /><span>最终字体、客户端版本、真实图片和交互仍以飞书实际预览为准</span></div><div class="preview-controls"><button data-device="mobile">手机</button><button data-device="desktop">桌面</button></div></div>
      <div class="preview-stage"><div id="device" class="device mobile"><div id="preview"></div></div></div>
      <div id="status" class="status">正在读取 spec…</div>
    </section>
  </main>
</div>
<script>
let appState = null;
let draft = null;
let latestCard = null;
let previewTimer = null;
let presetCatalog = [];
let sceneCatalog = [];

const $ = (id) => document.getElementById(id);
const clone = (value) => JSON.parse(JSON.stringify(value));
const esc = (value) => String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
const md = (value) => {
  let html = esc(value);
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\[([^\]]+)\]\(((?:https?:\/\/|lark:\/\/|feishu:\/\/)[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return html.replace(/\n/g, '<br>');
};

function pathParts(path) { return path.replace(/\[(\d+)\]/g, '.$1').split('.').filter(Boolean); }
function getPath(obj, path, fallback='') { let current=obj; for (const part of pathParts(path)) { if (current == null) return fallback; current=current[part]; } return current == null ? fallback : current; }
function setPath(obj, path, value) { const parts=pathParts(path); let current=obj; parts.forEach((part,i)=>{ if (i===parts.length-1) current[part]=value; else { if (current[part] == null) current[part]=/^\d+$/.test(parts[i+1])?[]:{}; current=current[part]; }}); }
function ensureArray(path) { const value=getPath(draft,path); if (!Array.isArray(value)) setPath(draft,path,[]); return getPath(draft,path); }
function setInput(path, value) { setPath(draft,path,value); schedulePreview(); }

function renderRepeater(containerId, path, fields, emptyFactory) {
  const container=$(containerId); const list=ensureArray(path); container.innerHTML='';
  list.forEach((item,index)=>{
    const box=document.createElement('div'); box.className='repeat-item';
    const head=document.createElement('div'); head.className='item-head'; head.innerHTML=`<span>#${index+1}</span><button class="remove" type="button">删除</button>`;
    head.querySelector('button').onclick=()=>{ list.splice(index,1); renderQuick(); schedulePreview(); };
    box.appendChild(head);
    const grid=document.createElement('div'); grid.className='repeat-grid';
    fields.forEach(field=>{
      const wrap=document.createElement('label'); wrap.className=field.full?'full':''; wrap.textContent=field.label;
      const control=document.createElement(field.multiline?'textarea':'input'); control.value=getPath(item,field.key,'');
      if (field.select) { const select=document.createElement('select'); select.innerHTML=field.select.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join(''); select.value=control.value; select.oninput=()=>{item[field.key]=select.value;schedulePreview();}; wrap.innerHTML=''; wrap.appendChild(document.createTextNode(field.label)); wrap.appendChild(select); grid.appendChild(wrap); return; }
      control.oninput=()=>{item[field.key]=control.value;schedulePreview();}; wrap.appendChild(control); grid.appendChild(wrap);
    });
    box.appendChild(grid); container.appendChild(box);
  });
}

function renderQuote() {
  const container=$('quoteEditor'); const quote=draft.quote;
  if (!quote || typeof quote!=='object') { container.innerHTML='<p class="hint">暂无引用。可在高级 JSON 中添加。</p>'; return; }
  container.innerHTML='';
  [['eyebrow','眉题',false],['title','标题',false],['text','内容',true]].forEach(([key,label,multiline])=>{
    const wrap=document.createElement('label'); wrap.className='field'; wrap.textContent=label;
    const control=document.createElement(multiline?'textarea':'input'); control.value=quote[key]||''; control.oninput=()=>{quote[key]=control.value;schedulePreview();}; wrap.appendChild(control); container.appendChild(wrap);
  });
  const wrap=document.createElement('label'); wrap.className='check-row'; wrap.innerHTML='<span>强调字号</span><input type="checkbox">'; wrap.querySelector('input').checked=quote.emphasis==='heading'; wrap.querySelector('input').onchange=()=>{quote.emphasis=wrap.querySelector('input').checked?'heading':'normal';schedulePreview();}; container.appendChild(wrap);
}

function renderDecisionSummary() {
  const plan=getPath(draft,'analysis.design_plan',null); const log=getPath(draft,'analysis.decision_log',[]); const box=$('decisionSummary');
  if(!plan || typeof plan!=='object') { box.innerHTML='<h3>AI 设计决策</h3><p class="hint">当前 spec 没有 design_plan；从原文重新生成即可获得可解释建议。</p>'; return; }
  const media=plan.media_policy||{}, fold=plan.fold_strategy||{}, nav=plan.navigation_strategy||{};
  const selected=(plan.component_strategy||[]).filter(item=>item.selected!==false).map(item=>item.component).join('、')||'section';
  const allocation=getPath(draft,'information_allocation',getPath(draft,'analysis.information_allocation',{}))||{};
  const image=allocation.image||{}; const buttons=allocation.buttons||{};
  const imageItems=Array.isArray(image.include)?image.include:[];
  const primary=buttons.primary&&buttons.primary.label?`主按钮：${buttons.primary.label}`:'';
  const secondary=Array.isArray(buttons.secondary)?buttons.secondary.length:0;
  const buttonState=buttons.use?`${primary||'已选按钮'}${secondary?`，次按钮 ${secondary} 个`:''}`:(Array.isArray(buttons.pending)&&buttons.pending.length?'检测到行动语句，但缺少真实目标':'不生成按钮');
  const reasons=(log||[]).slice(0,6).map(item=>`<li><strong>${esc(item.decision||'')}</strong> ${esc(item.component||'')}：${esc(item.reason||'')}</li>`).join('');
  box.innerHTML=`<h3>AI 设计决策</h3><div class="decision-grid"><div class="decision-item"><strong>视觉原型</strong>${esc(plan.visual_archetype||'-')} · ${esc(plan.recommended_preset||'-')}</div><div class="decision-item"><strong>组件选择</strong>${esc(selected)}</div><div class="decision-item"><strong>信息分工</strong>${image.use?`Seedream 5.0 Pro：${esc(image.job||'视觉关系')}`:'原生 Card：精简摘要；全文在 source.txt'} · 图片文字 ${imageItems.length} 项</div><div class="decision-item"><strong>图片建议</strong>${media.need_gallery?'多图组合':media.need_hero?'建议首图':'无需图片'} · ${esc(media.reason||'')}</div><div class="decision-item"><strong>按钮决策</strong>${esc(buttonState)}</div><div class="decision-item"><strong>折叠 / 导航</strong>${esc(fold.mode||'none')} · ${esc(nav.mode||'single_page')}${nav.requires_backend?'（需后端）':''}</div></div>${reasons?`<ul class="decision-reasons">${reasons}</ul>`:''}`;
}

function renderQuick() {
  const fields=['scene','preset','type','theme','width_mode','date_label','title','subtitle','eyebrow','lead','footer'];
  fields.forEach(id=>{ const el=$(id); if (el) el.value=getPath(draft,id,''); });
  const selectedScene=sceneCatalog.find(item=>item.id===getPath(draft,'scene',''));
  $('sceneHint').textContent=selectedScene ? `${selectedScene.name}：${selectedScene.goal} 推荐：${(selectedScene.recommended_blocks||[]).join('、')}` : '先选活动环节，系统会推荐版式配方和默认视觉风格。';
  const selectedPreset=presetCatalog.find(item=>item.id===getPath(draft,'preset',''));
  $('presetHint').textContent=selectedPreset ? `${selectedPreset.name}：${selectedPreset.short_description} 适用：${(selectedPreset.best_for||[]).join('、')}` : 'preset 负责色彩与视觉气质；scene 负责活动运营环节与内容配方。';
  ['timeline_focus','timeline_first','collapse_supporting','emoji_normalize'].forEach(id=>{$(id).checked=Boolean(getPath(draft,id,false));});
  $('hero_img_key').value=getPath(draft,'hero.img_key',''); $('hero_alt').value=getPath(draft,'hero.alt',''); $('hero_prompt').value=getPath(draft,'hero.prompt','');
  renderRepeater('factsList','facts',[{key:'label',label:'标签'},{key:'value',label:'值'}],()=>({label:'',value:''}));
  renderRepeater('sectionsList','sections',[{key:'title',label:'标题'},{key:'body',label:'正文',multiline:true,full:true}],()=>({title:'',body:''}));
  renderRepeater('timelineList','timeline',[{key:'date',label:'日期'},{key:'title',label:'阶段'},{key:'body',label:'细节',multiline:true,full:true}],()=>({date:'',title:'',body:''}));
  renderRepeater('buttonsList','buttons',[{key:'text',label:'按钮文字'},{key:'style',label:'样式',select:['primary','secondary','default','danger']},{key:'url',label:'URL',full:true}],()=>({text:'',style:'secondary',url:''}));
  renderQuote();
  $('advancedEditor').value=JSON.stringify(draft,null,2);
  $('sourceText').value=getPath(draft,'analysis.source_text','');
  $('link_mode').value=getPath(draft,'analysis.link_mode','button');
  renderDecisionSummary();
}

function bindQuickFields() {
  ['scene','preset','type','theme','width_mode','date_label','title','subtitle','eyebrow','lead','footer'].forEach(id=>{ const el=$(id); el.oninput=()=>setInput(id,el.value); });
  ['timeline_focus','timeline_first','collapse_supporting','emoji_normalize'].forEach(id=>{ const el=$(id); el.onchange=()=>setInput(id,el.checked); });
  ['hero_img_key','hero_alt','hero_prompt'].forEach(id=>{ const el=$(id); el.oninput=()=>{ if (!draft.hero || typeof draft.hero!=='object') draft.hero={}; draft.hero[id==='hero_img_key'?'img_key':id.replace('hero_','')]=el.value; schedulePreview(); }; });
}

function addItem(path, item) { ensureArray(path).push(item); renderQuick(); schedulePreview(); }
document.querySelectorAll('[data-add]').forEach(button=>button.addEventListener('click',()=>{
  const path=button.dataset.add; const defaults={facts:{label:'',value:''},sections:{title:'',body:''},timeline:{date:'',title:'',body:''},buttons:{text:'',style:'secondary',url:''}}; addItem(path,defaults[path]);
}));

function cssLength(value, fallback) { return /^\d+(?:\.\d+)?px(?:\s+\d+(?:\.\d+)?px){0,3}$/.test(value||'') ? value : fallback; }
function cssColor(value, fallback) { return /^(?:#[0-9a-f]{6}|rgba?\([\d.,\s]+\))$/i.test(value||'') ? value : fallback; }
function tokenColor(value) { return ({'brand_accent':'var(--accent)','brand_gold':'var(--gold)','brand_ink':'var(--ink)','yellow':'var(--gold)','red':'var(--vermilion)','green':'#426666','blue':'var(--blue)','turquoise':'var(--jade)','wathet':'#5AA4AE','indigo':'#425066','grey':'var(--muted)'})[value] || ''; }
function renderMarkdownNode(node) { const text=node.content || (node.text && node.text.content) || ''; const size=node.text_size || (node.text && node.text.text_size) || 'normal_v2'; const color=node.text_color || (node.text && node.text.text_color) || ''; const css=tokenColor(color); const style=css?` style="color:${css}"`:''; return `<div class="card-text ${esc(size)}"${style}>${md(text)}</div>`; }
function renderValue(value) { if (Array.isArray(value)) return value.map(renderValue).join(', '); if (value && typeof value==='object') return value.text || value.content || JSON.stringify(value); return value ?? ''; }
function surfaceColor(value) { return ({'grey-50':'#f6f2e9','grey-100':'#ebe8df','grey-200':'#e2ddd2'})[value] || '#f6f2e9'; }
function renderElement(node) {
  if (!node || typeof node!=='object') return '';
  const tag=node.tag;
  if (tag==='markdown') return renderMarkdownNode(node);
  if (tag==='div') return renderMarkdownNode({content:node.text?.content||'',text_size:node.text?.text_size||'notation',text_color:node.text?.text_color||''});
  if (tag==='hr') return '<hr class="card-hr">';
  if (tag==='img') { const src=node.local_preview_src; return src ? `<div class="image-preview-frame"><img src="${esc(src)}" alt="${esc(node.alt?.content||'功能性图片预览')}"></div>` : `<div class="image-placeholder">图片预览<br><small>${esc(node.img_key||'等待上传 img_key')}</small></div>`; }
  if (tag==='img_combination') return `<div class="image-combination ${esc(node.combination_mode||'double')}">${(node.img_list||[]).map(item=>`<div class="image-placeholder"><small>${esc(item?.img_key||'等待上传 img_key')}</small></div>`).join('')}</div>`;
  if (tag==='button') { const text=node.text?.content||''; return `<button class="card-button ${esc(node.type||'default')}">${esc(text)}</button>`; }
  if (tag==='column_set') { const mode=node.flex_mode||'stretch'; const gap=cssLength(node.horizontal_spacing,'8px'); return `<div class="card-columns ${esc(mode)}" style="gap:${gap}">${(node.columns||[]).map(renderElement).join('')}</div>`; }
  if (tag==='column') { const padding=cssLength(node.padding,'9px'); const gap=cssLength(node.vertical_spacing,'4px'); return `<div class="card-column" style="background:${surfaceColor(node.background_style)};padding:${padding};gap:${gap}">${(node.elements||[]).map(renderElement).join('')}</div>`; }
  if (tag==='collapsible_panel') { const title=node.header?.title?.content||'展开详情'; return `<details class="collapse-box"><summary>${esc(title)}</summary>${(node.elements||[]).map(renderElement).join('')}</details>`; }
  if (tag==='table') { const cols=node.columns||[]; const rows=node.rows||[]; return `<div class="table-box"><table class="preview-table"><thead><tr>${cols.map(c=>`<th>${esc(c.display_name||c.name||'')}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${cols.map(c=>`<td>${esc(renderValue(row?.[c.name]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`; }
  if (tag==='chart') { const type=node.chart_spec?.type||'chart'; return `<div class="chart-box"><strong>图表预览 · ${esc(type)}</strong><pre>${esc(JSON.stringify(node.chart_spec||{},null,2))}</pre></div>`; }
  if (tag==='form') return `<div class="form-box">${(node.elements||[]).map(renderElement).join('')}</div>`;
  if (tag==='input') return `<input disabled placeholder="${esc(node.placeholder?.content||'输入框')}" value="${esc(node.default_value||'')}">`;
  if (tag==='select_static' || tag==='multi_select_static') return `<select disabled><option>${esc(node.placeholder?.content||'选择一项')}</option>${(node.options||[]).map(o=>`<option>${esc(o.text?.content||o.text||'')}</option>`).join('')}</select>`;
  if (tag==='date_picker' || tag==='picker_time' || tag==='picker_datetime') return `<input disabled placeholder="${esc(node.placeholder?.content||'选择时间')}">`;
  if (tag==='checker') return `<label class="person-pill"><input type="checkbox" disabled ${node.checked?'checked':''}> ${esc(node.text?.content||'确认')}</label>`;
  if (tag==='person' || tag==='person_list') return `<span class="person-pill">成员 · ${esc(node.user_id||node.persons||'')}</span>`;
  if (tag==='overflow') return `<button class="card-button default">${esc(node.text?.content||'更多操作')}</button>`;
  return `<div class="card-text notation">未渲染组件：${esc(tag||'unknown')}</div>`;
}
function renderCard(card) {
  const header=card?.header||{}; const title=header.title?.content||''; const subtitle=header.subtitle?.content||''; const tag=header.text_tag_list?.[0]?.text?.content||''; const template=header.template||'grey';
  const body=card?.body?.elements||[]; const bodyPadding=cssLength(card?.body?.padding,'13px 13px 19px'); const bodyGap=cssLength(card?.body?.vertical_spacing,'9px');
  const accentValue=card?.config?.style?.color?.brand_accent?.light_mode; const accent=cssColor(accentValue,'#EACD76');
  $('preview').innerHTML=`<article class="feishu-card" style="--accent:${accent}"><header class="card-header ${esc(template)}"><div class="card-title">${esc(title)}</div>${subtitle?`<div class="card-subtitle">${esc(subtitle)}</div>`:''}${tag?`<span class="header-tag">${esc(tag)}</span>`:''}</header><section class="card-body" style="padding:${bodyPadding};gap:${bodyGap}">${body.map(renderElement).join('')}</section></article>`;
}

function showStatus(message, kind='') { const el=$('status'); el.textContent=message; el.className='status '+kind; }
async function request(path, method='GET', body=null) { const options={method,headers:{}}; if (body!==null) { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(body); } const response=await fetch(path,options); const data=await response.json(); if (!response.ok) throw new Error(data.error||'请求失败'); return data; }
async function refreshPreview() { try { const data=await request('/api/preview','POST',{spec:draft}); latestCard=data.card; renderCard(latestCard); const suffix=data.report?.sendable?'可编译':'有占位或需确认项'; showStatus(`预览已更新 · ${suffix}`,'ok'); } catch(error) { showStatus(error.message,'error'); } }
function schedulePreview() { clearTimeout(previewTimer); previewTimer=setTimeout(refreshPreview,320); }
async function save() { try { const data=await request('/api/save','POST',{spec:draft}); appState=data; latestCard=data.card; draft=clone(data.spec); renderQuick(); renderCard(latestCard); showStatus(`已保存并编译：${data.report.card}`,'ok'); } catch(error) { showStatus(error.message,'error'); } }
function download(name,data) { const blob=new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download=name; a.click(); URL.revokeObjectURL(url); }
async function copyCardKitCommand() { const command=appState?.report?.cardkit_import_command; if(!command) { showStatus('请先保存并编译，再复制 CardKit 导入命令。','error'); return; } try { await navigator.clipboard.writeText(command); showStatus(`已复制命令：${command}`,'ok'); } catch(error) { showStatus(`无法写入剪贴板，请手工复制：${command}`,'error'); } }

document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>{ document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t===tab)); document.querySelectorAll('.tab-pane').forEach(p=>p.classList.toggle('active',p.id===tab.dataset.tab+'Pane')); if(tab.dataset.tab==='advanced') $('advancedEditor').value=JSON.stringify(draft,null,2); }));
document.querySelectorAll('[data-device]').forEach(button=>button.addEventListener('click',()=>{ $('device').className='device '+button.dataset.device; }));
$('formatAdvanced').onclick=()=>{ try { $('advancedEditor').value=JSON.stringify(JSON.parse($('advancedEditor').value),null,2); showStatus('JSON 已格式化','ok'); } catch(error) { showStatus('JSON 格式错误：'+error.message,'error'); } };
$('applyAdvanced').onclick=()=>{ try { draft=JSON.parse($('advancedEditor').value); if(!draft || typeof draft!=='object' || Array.isArray(draft)) throw new Error('spec 必须是对象'); renderQuick(); schedulePreview(); showStatus('已应用高级 JSON，正在更新预览…'); } catch(error) { showStatus('无法应用 JSON：'+error.message,'error'); } };
 $('autoLayout').onclick=async()=>{ try { const text=$('sourceText').value.trim(); if(!text) throw new Error('请先粘贴一段原文'); const data=await request('/api/auto-layout','POST',{text,scene:getPath(draft,'scene',''),preset:getPath(draft,'preset',''),type:getPath(draft,'type',''),link_mode:$('link_mode').value}); draft=clone(data.spec); const preview=await request('/api/preview','POST',{spec:draft}); latestCard=preview.card; renderQuick(); renderCard(latestCard); showStatus(`已自动排版 · ${data.spec.analysis?.transformations?.length||0} 项可核对变换`,'ok'); } catch(error) { showStatus(error.message,'error'); } };
$('save').onclick=save; $('downloadSpec').onclick=()=>download('card.spec.json',draft); $('downloadCard').onclick=()=>download('card.card',latestCard||{}); $('copyCardKit').onclick=copyCardKitCommand;

async function boot() { try { const [state,presets,scenes]=await Promise.all([request('/api/state'),request('/api/presets'),request('/api/scenes')]); appState=state; presetCatalog=presets.presets||[]; sceneCatalog=scenes.scenes||[]; const presetSelect=$('preset'); presetSelect.innerHTML='<option value="">自动：跟随 scene / 默认风格</option>'+presetCatalog.map(item=>`<option value="${esc(item.id)}">${esc(item.name)} · ${esc(item.id)}</option>`).join(''); const sceneSelect=$('scene'); sceneSelect.innerHTML='<option value="">不指定环节</option>'+sceneCatalog.map(item=>`<option value="${esc(item.id)}">${esc(item.name)} · ${esc(item.id)}</option>`).join(''); draft=clone(appState.spec); latestCard=appState.card; bindQuickFields(); renderQuick(); renderCard(latestCard); showStatus('已加载。修改左侧字段即可实时预览。','ok'); } catch(error) { showStatus(error.message,'error'); } }
boot();
</script>
</body>
</html>"""


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read spec {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("spec root must be a JSON object")
    return value


def contains_tag(value: Any, tags: set[str]) -> bool:
    if isinstance(value, dict):
        if value.get("tag") in tags:
            return True
        return any(contains_tag(item, tags) for item in value.values())
    if isinstance(value, list):
        return any(contains_tag(item, tags) for item in value)
    return False


def contains_callback_behavior(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("tag") == "button":
            behaviors = value.get("behaviors")
            if isinstance(behaviors, list) and any(
                isinstance(behavior, dict) and behavior.get("type") == "callback" for behavior in behaviors
            ):
                return True
        return any(contains_callback_behavior(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_callback_behavior(item) for item in value)
    return False


def local_visual_output_ready(spec: Dict[str, Any], output_path: Path) -> bool:
    """Check a local Seedream PNG or Seedance GIF and its provenance."""
    motion_spec = spec.get("motion_spec") if isinstance(spec.get("motion_spec"), dict) else {}
    if bool(motion_spec.get("selected")):
        gif_path = output_path.parent / "hero.gif"
        provenance_path = output_path.parent / "hero-motion-generation.json"
        if not gif_path.is_file() or not provenance_path.is_file() or gif_path.read_bytes()[:6] not in {b"GIF87a", b"GIF89a"}:
            return False
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(provenance, dict):
            return False
        prompt_value = Path(str(provenance.get("prompt_file") or ""))
        prompt_file = prompt_value if prompt_value.is_absolute() else output_path.parent / prompt_value
        inspection = provenance.get("inspection") if isinstance(provenance.get("inspection"), dict) else {}
        return bool(
            str(provenance.get("generation_family") or "").lower().startswith("seedance")
            and str(provenance.get("tool") or "") in {"doubao.video_gen", "video_gen", "motion_gen", "animation_gen"}
            and provenance.get("asset_sha256") == hashlib.sha256(gif_path.read_bytes()).hexdigest()
            and provenance.get("asset_name") == "hero.gif"
            and str(provenance.get("output_format") or "").lower() == "gif"
            and bool(inspection.get("animated"))
            and int(inspection.get("frame_count") or 0) >= 2
            and prompt_file.is_file()
            and provenance.get("prompt_sha256") == hashlib.sha256(prompt_file.read_bytes()).hexdigest()
        )
    hero = spec.get("hero") if isinstance(spec, dict) else None
    generation_mode = str(
        (spec.get("image_generation_mode") if isinstance(spec, dict) else None)
        or (hero.get("image_generation_mode") if isinstance(hero, dict) else None)
        or ""
    ).strip()
    if generation_mode not in supported_image_modes():
        return False
    if not isinstance(hero, dict) or not isinstance(hero.get("functional_text"), list) or not hero.get("functional_text"):
        return False
    image_path = output_path.parent / "hero.png"
    provenance_path = output_path.parent / "hero-generation.json"
    from asset_validation import asset_error
    if asset_error(image_path, "PNG"):
        return False
    if not image_path.is_file() or not provenance_path.is_file():
        return False
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(provenance, dict):
        return False
    family = str(provenance.get("generation_family") or "").strip().lower()
    tool = str(provenance.get("tool") or "").strip()
    prompt_value = Path(str(provenance.get("prompt_file") or ""))
    prompt_file = prompt_value if prompt_value.is_absolute() else output_path.parent / prompt_value
    prompt_hash_ok = bool(provenance.get("prompt_sha256")) and prompt_file.is_file() and provenance.get("prompt_sha256") == hashlib.sha256(prompt_file.read_bytes()).hexdigest()
    expected_policy = image_mode_config(generation_mode).get("text_policy")
    return bool(
        provenance.get("generation_mode", generation_mode) == generation_mode
        and provenance.get("text_policy") == expected_policy
        and family.startswith("seedream")
        and (tool in {"doubao.image_gen", "image_gen", "seedream"} or tool.endswith(".image_gen"))
        and provenance.get("image_sha256") == hashlib.sha256(image_path.read_bytes()).hexdigest()
        and prompt_hash_ok
    )


def inject_local_visual(card: Dict[str, Any], *, ready: bool = False) -> Dict[str, Any]:
    """Show the complete Seedream PNG or Seedance GIF in local preview."""
    if not ready:
        return card
    display_card = json.loads(json.dumps(card, ensure_ascii=False))
    elements = display_card.get("body", {}).get("elements")
    if not isinstance(elements, list):
        return display_card
    for element in elements:
        if isinstance(element, dict) and element.get("tag") == "img":
            element["local_preview_src"] = "/api/visual"
            return display_card
    preview_image = {
        "tag": "img",
        "img_key": "local-visual-preview",
        "alt": {"tag": "plain_text", "content": "图片内含时间、阶段与动作信息"},
        "local_preview_src": "/api/visual",
    }
    insert_at = next(
        (index for index, element in enumerate(elements) if isinstance(element, dict) and element.get("tag") == "collapsible_panel"),
        0,
    )
    elements.insert(insert_at, preview_image)
    return display_card


class EditorState:
    def __init__(self, spec_path: Path, output_path: Path, editable_spec_path: Path) -> None:
        self.spec_path = spec_path
        self.output_path = output_path
        self.editable_spec_path = editable_spec_path
        self.spec = load_json(spec_path)
        self.card: Dict[str, Any] = {}

    def surface_for(self, card: Dict[str, Any], spec: Dict[str, Any]) -> str:
        requested = spec.get("surface")
        if requested in {"raw", "custom-bot", "application-bot"}:
            return requested
        if contains_tag(card, {"form", "input", "select_static", "multi_select_static", "date_picker", "picker_time", "picker_datetime"}):
            return "application-bot"
        if contains_tag(card, {"button"}) and contains_callback_behavior(card):
            return "application-bot"
        return "custom-bot"

    def preview(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            raise ValueError("spec root must be a JSON object")
        card, hero_plan, contracts = build_card(spec, self.output_path, persist_assets=False)
        hero_pending = isinstance(spec.get("hero"), dict) and not str(spec.get("hero", {}).get("img_key") or "").strip()
        surface = "application-bot" if contracts else self.surface_for(card, spec)
        qa = validate(card, surface=surface, allow_placeholders=True)
        resolved_scene = resolve_scene(spec)
        resolved_preset = resolve_preset(spec, resolved_scene)
        scene_contract = scene_contract_report(spec, resolved_scene)
        motion_selected = bool((spec.get("motion_spec") or {}).get("selected")) if isinstance(spec.get("motion_spec"), dict) else False
        local_image = self.output_path.parent / ("hero.gif" if motion_selected else "hero.png")
        local_image_ready = local_visual_output_ready(spec, self.output_path)
        display_card = inject_local_visual(card, ready=local_image_ready)
        report = {
            "card": str(self.output_path),
            "editable_spec": str(self.editable_spec_path),
            "scene": resolved_scene.get("id") if resolved_scene else None,
            "preset": resolved_preset.get("id") if resolved_preset else None,
            "callbacks": len(contracts),
            "surface": surface,
            "content_analysis": spec.get("analysis") if isinstance(spec.get("analysis"), dict) else None,
            "design_plan": spec.get("analysis", {}).get("design_plan") if isinstance(spec.get("analysis"), dict) else None,
            "decision_log": spec.get("analysis", {}).get("decision_log", []) if isinstance(spec.get("analysis"), dict) else [],
            "scene_contract": scene_contract,
            "sendable": qa["ok"] and not contains_placeholder(card) and not bool(hero_plan) and not hero_pending and (scene_contract is None or scene_contract["ok"]),
            "asset_plan_required": hero_pending,
            "local_visual": {
                "path": str(local_image),
                "kind": "gif" if motion_selected else "image",
                "displayed": local_image_ready,
                "embedded_in_saved_card": bool(contains_tag(card, {"img"})),
            },
            "validation": qa,
            "cardkit_import_command": f"python3 scripts/feishu_cli.py create-cardkit --card {shlex.quote(str(self.output_path))} --as bot --dry-run",
        }
        return {"spec": spec, "card": display_card, "report": report}

    def save(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            raise ValueError("spec root must be a JSON object")
        card, report = compile_outputs(spec, self.output_path, editable_spec=self.editable_spec_path)
        self.spec = spec
        self.card = card
        result = self.preview(spec)
        for key in ("card", "editable_spec", "callbacks", "asset_plan", "interaction_contract", "preview_command"):
            result["report"][key] = report.get(key)
        result["report"]["compile"] = report
        return result


class ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server: ReusableHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("preview_card: " + (format % args) + "\n")

    @property
    def state(self) -> EditorState:
        return self.server.editor_state  # type: ignore[attr-defined]

    def send_json(self, value: Any, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            payload = EDITOR_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if parsed.path == "/api/state":
            try:
                self.send_json(self.state.preview(self.state.spec))
            except (OSError, ValueError, KeyError) as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/visual":
            motion_spec = self.state.spec.get("motion_spec") if isinstance(self.state.spec.get("motion_spec"), dict) else {}
            motion_selected = bool(motion_spec.get("selected"))
            image_path = self.state.output_path.parent / ("hero.gif" if motion_selected else "hero.png")
            if not image_path.is_file():
                self.send_json({"error": "the selected local image is not available; generate the Seedream 5.0 Pro image first"}, 404)
                return
            payload = image_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/gif" if motion_selected else "image/png")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if parsed.path == "/api/presets":
            try:
                registry = load_preset_registry()
                self.send_json({"default": registry.get("default"), "presets": registry.get("presets", [])})
            except (OSError, ValueError, KeyError) as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/scenes":
            try:
                registry = load_scene_registry()
                self.send_json({"default": registry.get("default"), "scenes": registry.get("scenes", [])})
            except (OSError, ValueError, KeyError) as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/download":
            kind = parse_qs(parsed.query).get("kind", [""])[0]
            path = self.state.editable_spec_path if kind == "spec" else self.state.output_path if kind == "card" else None
            if path is None or not path.exists():
                self.send_json({"error": "download target not found"}, 404)
                return
            payload = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/api/preview", "/api/save", "/api/auto-layout"}:
            self.send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/auto-layout":
                if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                    raise ValueError("auto-layout needs a text string")
                requested_type = payload.get("type") if payload.get("type") not in {None, "", "custom"} else None
                requested_scene = payload.get("scene") or None
                requested_preset = payload.get("preset") or None
                spec = build_auto_spec(
                    payload["text"],
                    requested_type=requested_type,
                    requested_scene=requested_scene,
                    requested_preset=requested_preset,
                    link_mode=payload.get("link_mode", "button"),
                )
                self.send_json({"spec": spec, "analysis": spec.get("analysis", {})})
                return
            spec = payload.get("spec") if isinstance(payload, dict) else None
            if self.path == "/api/save":
                self.send_json(self.state.save(spec))
            else:
                self.send_json(self.state.preview(spec))
        except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
            self.send_json({"error": str(exc)}, 400)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False, description="Serve a local editable Feishu Card preview")
    parser.add_argument("--spec", required=True, help="source spec JSON")
    parser.add_argument("--output", required=True, help="compiled .card output")
    parser.add_argument("--spec-output", help="editable spec path; defaults to an existing *.spec.json or a sibling path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="open the local preview in the default browser")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        spec_path = Path(args.spec).expanduser().resolve()
        output_path = Path(args.output).expanduser().resolve()
        if args.spec_output:
            editable_spec_path = Path(args.spec_output).expanduser().resolve()
        elif spec_path.name.endswith(".spec.json"):
            editable_spec_path = spec_path
        else:
            editable_spec_path = output_path.with_suffix(".spec.json")
        state = EditorState(spec_path, output_path, editable_spec_path)
        server = ReusableHTTPServer((args.host, args.port), Handler)
        server.editor_state = state  # type: ignore[attr-defined]
        visible_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
        url = f"http://{visible_host}:{args.port}/"
        print(f"Editable Feishu card preview: {url}")
        print(f"Source spec: {editable_spec_path}")
        print("Press Ctrl-C to stop. Save in the browser writes the spec and card locally.")
        if args.open:
            webbrowser.open(url)
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        print(f"preview_card.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

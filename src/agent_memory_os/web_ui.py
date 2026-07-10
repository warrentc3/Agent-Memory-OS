"""Static single-page console for the AgentMemoryOS Web UI.

The page is served as-is and talks to the JSON API with fetch; all dynamic
values are inserted client-side via textContent, so memory content can never
inject markup. Kept as a plain Python string to preserve the zero-build,
zero-packaging deployment story.
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentMemoryOS Web UI</title>
<style>
  :root {
    --bg: #f6f7fb; --panel: #ffffff; --panel-2: #f0f2f8;
    --text: #1c2030; --muted: #6b7390; --border: #e2e6f0;
    --accent: #6d3df0; --accent-soft: #efeafe;
    --good: #178a50; --warn: #b3711d; --bad: #c23a3a;
    --shadow: 0 1px 2px rgba(20, 24, 40, .05), 0 8px 24px rgba(20, 24, 40, .06);
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0d1020; --panel: #151a30; --panel-2: #1b2140;
      --text: #e8ebf7; --muted: #8f97b8; --border: #262e52;
      --accent: #9a7bff; --accent-soft: #2a2352;
      --good: #4cc98a; --warn: #e3a45a; --bad: #ec7b7b;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35);
      color-scheme: dark;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.55 Inter, "SF Pro Text", ui-sans-serif, system-ui, "Segoe UI", sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 10;
    background: color-mix(in srgb, var(--bg) 88%, transparent);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
  }
  .bar {
    max-width: 1080px; margin: 0 auto; padding: 14px 24px;
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 17px; }
  .brand .logo {
    width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center;
    background: linear-gradient(135deg, var(--accent), #b96bff); color: #fff; font-size: 15px;
  }
  .stats { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip {
    padding: 4px 12px; border-radius: 999px; font-size: 12.5px;
    background: var(--panel-2); border: 1px solid var(--border); color: var(--muted);
  }
  .chip b { color: var(--text); font-variant-numeric: tabular-nums; }
  .acting { margin-left: auto; display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
  .acting input {
    width: 150px; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--panel); color: var(--text); font-size: 13px;
  }
  nav.tabs {
    max-width: 1080px; margin: 0 auto; padding: 0 24px;
    display: flex; gap: 4px;
  }
  nav.tabs button {
    appearance: none; background: none; border: none; cursor: pointer;
    padding: 10px 14px; font-size: 14px; font-weight: 600; color: var(--muted);
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  nav.tabs button.active { color: var(--accent); border-bottom-color: var(--accent); }
  main { max-width: 1080px; margin: 0 auto; padding: 24px; }
  section.tab { display: none; }
  section.tab.active { display: block; }

  .searchrow { display: flex; gap: 10px; margin-bottom: 18px; }
  .searchrow input[type=search] {
    flex: 1; padding: 12px 16px; font-size: 15px; border-radius: 12px;
    border: 1px solid var(--border); background: var(--panel); color: var(--text);
    box-shadow: var(--shadow);
  }
  .searchrow input[type=search]:focus, input:focus, select:focus, textarea:focus {
    outline: 2px solid color-mix(in srgb, var(--accent) 45%, transparent); outline-offset: 0;
    border-color: var(--accent);
  }
  button.primary {
    padding: 10px 20px; border-radius: 12px; border: none; cursor: pointer;
    background: var(--accent); color: #fff; font-weight: 650; font-size: 14.5px;
  }
  button.primary:hover { filter: brightness(1.08); }
  button.ghost {
    padding: 8px 14px; border-radius: 10px; cursor: pointer; font-size: 13px; font-weight: 600;
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
  }
  button.ghost:hover { border-color: var(--accent); color: var(--accent); }

  .cards { display: flex; flex-direction: column; gap: 14px; }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
    padding: 16px 18px; box-shadow: var(--shadow);
  }
  .card .top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .badge {
    font-size: 11.5px; font-weight: 700; letter-spacing: .3px; text-transform: uppercase;
    padding: 3px 9px; border-radius: 999px; border: 1px solid transparent;
  }
  .badge.scope-user    { background: #e8f0fe; color: #2456c4; }
  .badge.scope-agent   { background: #e2f6f2; color: #0e7a63; }
  .badge.scope-project { background: #fdf1dc; color: #94660d; }
  .badge.scope-team    { background: #fde8f1; color: #b02a6c; }
  .badge.scope-global  { background: #e6f6e8; color: #1e7d33; }
  @media (prefers-color-scheme: dark) {
    .badge.scope-user    { background: #1d2c52; color: #92b4ff; }
    .badge.scope-agent   { background: #12352f; color: #5ad4b8; }
    .badge.scope-project { background: #3a2d12; color: #eec272; }
    .badge.scope-team    { background: #3c1830; color: #f18ebc; }
    .badge.scope-global  { background: #14311c; color: #6fd487; }
  }
  .badge.type { background: none; border-color: var(--border); color: var(--muted); }
  .owner { font-size: 12.5px; color: var(--muted); }
  .owner b { color: var(--text); font-weight: 600; }
  .pin { font-size: 13px; }
  .scorewrap { margin-left: auto; display: flex; align-items: center; gap: 8px; }
  .scorebar { width: 90px; height: 6px; border-radius: 3px; background: var(--panel-2); overflow: hidden; }
  .scorebar i { display: block; height: 100%; background: linear-gradient(90deg, var(--accent), #b96bff); border-radius: 3px; }
  .scoreval { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .content { white-space: pre-wrap; word-break: break-word; font-size: 14.5px; }
  .meta { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-top: 10px; font-size: 12px; color: var(--muted); }
  .tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .tag { background: var(--accent-soft); color: var(--accent); padding: 2px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 600; }
  .gauge { display: inline-flex; align-items: center; gap: 5px; }
  .gauge .dotbar { width: 44px; height: 4px; border-radius: 2px; background: var(--panel-2); overflow: hidden; }
  .gauge .dotbar i { display: block; height: 100%; background: var(--muted); }
  .card .actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  .card .actions button {
    font-size: 12.5px; padding: 5px 12px; border-radius: 8px; cursor: pointer;
    background: var(--panel-2); border: 1px solid var(--border); color: var(--muted); font-weight: 600;
  }
  .card .actions button:hover { color: var(--text); border-color: var(--muted); }
  .card .actions button.danger:hover { color: var(--bad); border-color: var(--bad); }
  .reason { margin-top: 8px; font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--muted); word-break: break-all; display: none; }
  .linksbox { margin-top: 10px; display: none; border-top: 1px dashed var(--border); padding-top: 10px; font-size: 12.5px; color: var(--muted); }
  .linksbox .linkrow { display: flex; gap: 8px; align-items: center; padding: 3px 0; }
  .linksbox .rel { font-weight: 700; color: var(--accent); }
  .empty { text-align: center; color: var(--muted); padding: 48px 0; }
  .empty .big { font-size: 34px; margin-bottom: 8px; }

  form.addform {
    background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
    padding: 22px; box-shadow: var(--shadow); display: grid; gap: 16px;
    grid-template-columns: 1fr 1fr;
  }
  form.addform .full { grid-column: 1 / -1; }
  label.field { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; font-weight: 650; color: var(--muted); }
  label.field input[type=text], label.field select, label.field textarea, label.field input[type=datetime-local] {
    padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border);
    background: var(--panel-2); color: var(--text); font-size: 14px; font-family: inherit;
  }
  label.field textarea { min-height: 110px; resize: vertical; }
  .sliderrow { display: flex; align-items: center; gap: 10px; }
  .sliderrow input[type=range] { flex: 1; accent-color: var(--accent); }
  .sliderrow output { width: 38px; text-align: right; font-variant-numeric: tabular-nums; color: var(--text); }
  .checks { display: flex; gap: 22px; align-items: center; font-size: 13.5px; color: var(--text); }
  .checks label { display: flex; gap: 7px; align-items: center; font-weight: 500; }
  .checks input { accent-color: var(--accent); width: 16px; height: 16px; }

  .toolgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .tool { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 20px; box-shadow: var(--shadow); }
  .tool h3 { margin: 0 0 4px; font-size: 15px; }
  .tool p.hint { margin: 0 0 14px; font-size: 12.5px; color: var(--muted); }
  .tool .row { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .tool input, .tool select {
    padding: 8px 11px; border-radius: 9px; border: 1px solid var(--border);
    background: var(--panel-2); color: var(--text); font-size: 13px; flex: 1; min-width: 120px;
  }
  .packtext {
    white-space: pre-wrap; word-break: break-word; background: var(--panel-2);
    border-radius: 12px; padding: 14px; font: 12.5px/1.6 ui-monospace, Menlo, monospace;
    max-height: 320px; overflow: auto; margin-top: 10px;
  }
  .decisions { margin-top: 10px; font-size: 12px; }
  .decisions .drow { display: flex; gap: 8px; align-items: baseline; padding: 4px 0; border-bottom: 1px dashed var(--border); }
  .decisions .ok { color: var(--good); font-weight: 700; }
  .decisions .no { color: var(--muted); }

  .loadmore { display: flex; justify-content: center; margin-top: 16px; }
  #toasts { position: fixed; right: 20px; bottom: 20px; display: flex; flex-direction: column; gap: 8px; z-index: 99; }
  .toast {
    background: var(--panel); border: 1px solid var(--border); border-left: 3px solid var(--accent);
    padding: 11px 16px; border-radius: 12px; box-shadow: var(--shadow); font-size: 13.5px;
    max-width: 360px; animation: slidein .18s ease-out;
  }
  .toast.err { border-left-color: var(--bad); }
  .toast.ok { border-left-color: var(--good); }
  @keyframes slidein { from { transform: translateY(8px); opacity: 0; } to { transform: none; opacity: 1; } }
  @media (max-width: 720px) {
    form.addform, .toolgrid { grid-template-columns: 1fr; }
    .acting { margin-left: 0; width: 100%; }
  }
</style>
</head>
<body>
<header>
  <div class="bar">
    <div class="brand"><span class="logo">◈</span> AgentMemoryOS <span style="font-weight:400;color:var(--muted);font-size:13px">Web UI</span></div>
    <div class="stats">
      <span class="chip">Total memories <b id="stat-total">–</b></span>
      <span class="chip">Links <b id="stat-links">–</b></span>
    </div>
    <div class="acting">
      <span title="Requester identity used for search, context packs and feedback. Empty = unrestricted admin view.">Acting as</span>
      <input id="acting-as" type="text" placeholder="admin (all)" autocomplete="off">
    </div>
  </div>
  <nav class="tabs">
    <button data-tab="search" class="active">Search</button>
    <button data-tab="browse">Browse</button>
    <button data-tab="add">Add memory</button>
    <button data-tab="tools">Tools</button>
  </nav>
</header>

<main>
  <section class="tab active" id="tab-search">
    <div class="searchrow">
      <input id="q" type="search" placeholder="Search memories… (associative recall included)">
      <button class="primary" id="btn-search">Search</button>
    </div>
    <div class="cards" id="search-results">
      <div class="empty"><div class="big">◈</div>Search your agent's memory.<br>Results resonate through linked memories, gated by the acting identity.</div>
    </div>
  </section>

  <section class="tab" id="tab-browse">
    <div class="cards" id="browse-results"></div>
    <div class="loadmore"><button class="ghost" id="btn-more">Load more</button></div>
  </section>

  <section class="tab" id="tab-add">
    <form class="addform" id="add-form">
      <label class="field full">Content
        <textarea id="f-content" required placeholder="What should be remembered?"></textarea>
      </label>
      <label class="field">Owner
        <input type="text" id="f-owner" value="default">
      </label>
      <label class="field">Scope
        <select id="f-scope">
          <option>user</option><option>agent</option><option>project</option>
          <option>team</option><option>global</option>
        </select>
      </label>
      <label class="field">Type
        <select id="f-type">
          <option>note</option><option>preference</option><option>fact</option>
          <option>procedure</option><option>environment</option><option>decision</option>
          <option>warning</option>
        </select>
      </label>
      <label class="field">Tags <span style="font-weight:400">(comma separated)</span>
        <input type="text" id="f-tags" placeholder="deploy, checklist">
      </label>
      <label class="field full">Visibility <span style="font-weight:400">(comma separated: <code>global</code>, <code>agent:neo</code>, <code>team:core</code> — empty = owner only)</span>
        <input type="text" id="f-visibility" placeholder="owner only">
      </label>
      <label class="field">Importance
        <span class="sliderrow"><input type="range" id="f-importance" min="0" max="1" step="0.05" value="0.5"><output id="o-importance">0.50</output></span>
      </label>
      <label class="field">Confidence
        <span class="sliderrow"><input type="range" id="f-confidence" min="0" max="1" step="0.05" value="0.8"><output id="o-confidence">0.80</output></span>
      </label>
      <label class="field">Expires at <span style="font-weight:400">(optional)</span>
        <input type="datetime-local" id="f-expires">
      </label>
      <div class="field checks" style="justify-content:flex-start; padding-top: 22px;">
        <label><input type="checkbox" id="f-pinned"> Pinned</label>
        <label><input type="checkbox" id="f-autolink" checked> Auto-link similar</label>
      </div>
      <div class="full" style="display:flex;justify-content:flex-end">
        <button class="primary" type="submit">Save memory</button>
      </div>
    </form>
  </section>

  <section class="tab" id="tab-tools">
    <div class="toolgrid">
      <div class="tool" style="grid-column: 1 / -1;">
        <h3>Context pack preview</h3>
        <p class="hint">Exactly what would be injected into the prompt for the acting identity, with per-memory decisions.</p>
        <div class="row">
          <input id="pack-q" type="text" placeholder="Query">
          <input id="pack-tokens" type="number" value="1200" min="32" max="32000" style="max-width:110px">
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--muted)"><input type="checkbox" id="pack-reinforce" style="accent-color:var(--accent)"> auto-reinforce</label>
          <button class="ghost" id="btn-pack">Build pack</button>
        </div>
        <div id="pack-out"></div>
      </div>
      <div class="tool">
        <h3>Link two memories</h3>
        <p class="hint">Authoritative association edge; resonance recall follows it.</p>
        <div class="row"><input id="link-src" type="text" placeholder="src memory id"></div>
        <div class="row"><input id="link-dst" type="text" placeholder="dst memory id"></div>
        <div class="row">
          <select id="link-rel">
            <option>related_to</option><option>caused_by</option><option>supersedes</option>
            <option>derived_from</option><option>co_recalled</option>
          </select>
          <input id="link-weight" type="number" value="0.5" min="0" max="1" step="0.1" style="max-width:90px">
          <button class="ghost" id="btn-link">Link</button>
        </div>
      </div>
      <div class="tool">
        <h3>Consolidate</h3>
        <p class="hint">Merge exact duplicates and synthesize strongly co-recalled clusters into concept memories. Visibility boundaries are never crossed.</p>
        <button class="ghost" id="btn-consolidate">Run consolidation</button>
        <div id="consolidate-out" style="margin-top:10px;font-size:13px;color:var(--muted)"></div>
      </div>
    </div>
  </section>
</main>

<div id="toasts"></div>

<script>
"use strict";
const $ = (id) => document.getElementById(id);
const actingAs = () => $("acting-as").value.trim();
$("acting-as").value = localStorage.getItem("amos.actingAs") || "";
$("acting-as").addEventListener("change", () => localStorage.setItem("amos.actingAs", actingAs()));

function toast(message, kind) {
  const node = document.createElement("div");
  node.className = "toast" + (kind ? " " + kind : "");
  node.textContent = message;
  $("toasts").appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

async function api(path, options) {
  const response = await fetch(path, options);
  let body = null;
  try { body = await response.json(); } catch (e) { /* empty body */ }
  if (!response.ok) {
    const detail = body && (body.detail || body.error) ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body.error)) : ("HTTP " + response.status);
    throw new Error(detail);
  }
  return body;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

async function loadStats() {
  try {
    const stats = await api("/api/stats");
    $("stat-total").textContent = stats.total;
    $("stat-links").textContent = stats.links;
  } catch (e) { /* header stays as dashes */ }
}

/* ---------- tabs ---------- */
document.querySelectorAll("nav.tabs button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll("section.tab").forEach((s) => s.classList.remove("active"));
    button.classList.add("active");
    $("tab-" + button.dataset.tab).classList.add("active");
    if (button.dataset.tab === "browse" && !browseLoaded) refreshBrowse();
  });
});

/* ---------- memory cards ---------- */
function gauge(label, value) {
  const wrap = el("span", "gauge");
  wrap.appendChild(el("span", null, label));
  const bar = el("span", "dotbar");
  const fill = el("i");
  fill.style.width = Math.round(value * 100) + "%";
  bar.appendChild(fill);
  wrap.appendChild(bar);
  wrap.appendChild(el("span", null, value.toFixed(2)));
  return wrap;
}

function renderCard(memory, extras) {
  const card = el("article", "card");
  const top = el("div", "top");
  top.appendChild(el("span", "badge scope-" + memory.scope, memory.scope));
  top.appendChild(el("span", "badge type", memory.type));
  const owner = el("span", "owner");
  owner.appendChild(document.createTextNode("by "));
  owner.appendChild(el("b", null, memory.owner));
  top.appendChild(owner);
  if (memory.pinned) top.appendChild(el("span", "pin", "📌"));
  if (!memory.visibility || memory.visibility.length === 0) {
    top.appendChild(el("span", "owner", "🔒 private"));
  }
  if (extras && typeof extras.score === "number") {
    const wrap = el("span", "scorewrap");
    const bar = el("span", "scorebar");
    const fill = el("i");
    fill.style.width = Math.max(4, Math.round((extras.score / extras.maxScore) * 100)) + "%";
    bar.appendChild(fill);
    wrap.appendChild(bar);
    wrap.appendChild(el("span", "scoreval", extras.score.toFixed(3)));
    top.appendChild(wrap);
  }
  card.appendChild(top);
  card.appendChild(el("div", "content", memory.content));

  const meta = el("div", "meta");
  if (memory.tags && memory.tags.length) {
    const tags = el("span", "tags");
    memory.tags.slice(0, 6).forEach((t) => tags.appendChild(el("span", "tag", t)));
    meta.appendChild(tags);
  }
  meta.appendChild(gauge("imp", memory.importance));
  meta.appendChild(gauge("conf", memory.confidence));
  meta.appendChild(el("span", null, "updated " + new Date(memory.updated_at).toLocaleString()));
  if (memory.expires_at) meta.appendChild(el("span", null, "expires " + new Date(memory.expires_at).toLocaleString()));
  card.appendChild(meta);

  const actions = el("div", "actions");
  const helpfulBtn = el("button", null, "👍 Helpful");
  helpfulBtn.addEventListener("click", () => feedback(memory.id, true));
  const misleadingBtn = el("button", null, "👎 Misleading");
  misleadingBtn.addEventListener("click", () => feedback(memory.id, false));
  const linksBtn = el("button", null, "🔗 Links");
  const copyBtn = el("button", null, "⧉ Copy id");
  copyBtn.addEventListener("click", () => { navigator.clipboard.writeText(memory.id); toast("Copied " + memory.id, "ok"); });
  const deleteBtn = el("button", "danger", "🗑 Delete");
  deleteBtn.addEventListener("click", async () => {
    if (!confirm("Delete this memory permanently?\n\n" + memory.content.slice(0, 120))) return;
    try {
      await api("/api/memories/" + memory.id, { method: "DELETE" });
      card.remove(); loadStats(); toast("Memory deleted", "ok");
    } catch (e) { toast(e.message, "err"); }
  });
  actions.append(helpfulBtn, misleadingBtn, linksBtn, copyBtn, deleteBtn);
  if (extras && extras.reason) {
    const whyBtn = el("button", null, "why?");
    const reason = el("div", "reason", extras.reason);
    whyBtn.addEventListener("click", () => { reason.style.display = reason.style.display === "block" ? "none" : "block"; });
    actions.appendChild(whyBtn);
    card.appendChild(actions);
    card.appendChild(reason);
  } else {
    card.appendChild(actions);
  }

  const linksBox = el("div", "linksbox");
  linksBtn.addEventListener("click", async () => {
    if (linksBox.style.display === "block") { linksBox.style.display = "none"; return; }
    linksBox.textContent = "Loading…"; linksBox.style.display = "block";
    try {
      const data = await api("/api/memories/" + memory.id + "/links");
      linksBox.textContent = "";
      if (!data.links.length) { linksBox.textContent = "No links yet."; return; }
      for (const link of data.links) {
        const other = link.src_id === memory.id ? link.dst_id : link.src_id;
        const row = el("div", "linkrow");
        row.appendChild(el("span", "rel", link.relation));
        const detail = await api("/api/memories/" + other).catch(() => null);
        row.appendChild(el("span", null, detail ? detail.content.slice(0, 80) : other));
        row.appendChild(el("span", null, "w=" + link.weight.toFixed(2)));
        linksBox.appendChild(row);
      }
    } catch (e) { linksBox.textContent = e.message; }
  });
  card.appendChild(linksBox);
  return card;
}

async function feedback(memoryId, helpful) {
  try {
    const body = { memory_ids: [memoryId], helpful: helpful };
    if (actingAs()) body.requester_agent_id = actingAs();
    await api("/api/recall", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    toast(helpful ? "Reinforced — will surface more readily." : "Weakened — confidence and links reduced.", "ok");
  } catch (e) { toast(e.message, "err"); }
}

/* ---------- search ---------- */
async function runSearch() {
  const query = $("q").value.trim();
  if (!query) return;
  const container = $("search-results");
  container.innerHTML = ""; container.appendChild(el("div", "empty", "Searching…"));
  const params = new URLSearchParams({ q: query, limit: "20" });
  if (actingAs()) params.set("requester_agent_id", actingAs());
  try {
    const data = await api("/api/search?" + params);
    container.innerHTML = "";
    if (!data.results.length) {
      const empty = el("div", "empty");
      empty.appendChild(el("div", "big", "∅"));
      empty.appendChild(document.createTextNode("Nothing recalled for that query" + (actingAs() ? " as “" + actingAs() + "”." : ".")));
      container.appendChild(empty);
      return;
    }
    const maxScore = Math.max(...data.results.map((r) => r.score), 0.0001);
    for (const result of data.results) {
      container.appendChild(renderCard(result, { score: result.score, maxScore: maxScore, reason: result.reason }));
    }
  } catch (e) { container.innerHTML = ""; toast(e.message, "err"); }
}
$("btn-search").addEventListener("click", runSearch);
$("q").addEventListener("keydown", (event) => { if (event.key === "Enter") runSearch(); });

/* ---------- browse ---------- */
let browseLoaded = false;
let browseOffset = 0;
async function refreshBrowse(more) {
  browseLoaded = true;
  if (!more) { browseOffset = 0; $("browse-results").innerHTML = ""; }
  const params = new URLSearchParams({ limit: "20", offset: String(browseOffset) });
  if (actingAs()) params.set("requester_agent_id", actingAs());
  try {
    const data = await api("/api/memories?" + params);
    const container = $("browse-results");
    if (!data.memories.length && browseOffset === 0) {
      const empty = el("div", "empty");
      empty.appendChild(el("div", "big", "☁"));
      empty.appendChild(document.createTextNode("No memories yet. Add the first one."));
      container.appendChild(empty);
    }
    for (const memory of data.memories) container.appendChild(renderCard(memory, null));
    browseOffset += data.memories.length;
    $("btn-more").style.display = data.memories.length < 20 ? "none" : "inline-block";
  } catch (e) { toast(e.message, "err"); }
}
$("btn-more").addEventListener("click", () => refreshBrowse(true));

/* ---------- add ---------- */
$("f-importance").addEventListener("input", (e) => { $("o-importance").textContent = Number(e.target.value).toFixed(2); });
$("f-confidence").addEventListener("input", (e) => { $("o-confidence").textContent = Number(e.target.value).toFixed(2); });
$("add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const expiresRaw = $("f-expires").value;
  const payload = {
    content: $("f-content").value,
    owner: $("f-owner").value || "default",
    scope: $("f-scope").value,
    type: $("f-type").value,
    tags: $("f-tags").value.split(",").map((t) => t.trim()).filter(Boolean),
    visibility: $("f-visibility").value.split(",").map((v) => v.trim()).filter(Boolean),
    importance: Number($("f-importance").value),
    confidence: Number($("f-confidence").value),
    pinned: $("f-pinned").checked,
    auto_link: $("f-autolink").checked,
  };
  if (expiresRaw) payload.expires_at = new Date(expiresRaw).toISOString();
  try {
    const saved = await api("/api/memories", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
    toast("Saved " + saved.id, "ok");
    $("f-content").value = ""; $("f-tags").value = "";
    loadStats(); browseLoaded = false;
  } catch (e) { toast(e.message, "err"); }
});

/* ---------- tools ---------- */
$("btn-pack").addEventListener("click", async () => {
  const query = $("pack-q").value.trim();
  if (!query) return;
  const params = new URLSearchParams({ q: query, max_tokens: $("pack-tokens").value });
  if (actingAs()) params.set("requester_agent_id", actingAs());
  if ($("pack-reinforce").checked) params.set("auto_reinforce", "true");
  const out = $("pack-out");
  out.textContent = "Building…";
  try {
    const data = await api("/api/context-pack?" + params);
    out.innerHTML = "";
    out.appendChild(el("div", null, "")).append(
      Object.assign(el("span", "chip"), { textContent: data.used_tokens + " / " + data.max_tokens + " tokens" })
    );
    out.appendChild(el("pre", "packtext", data.text));
    const decisions = el("div", "decisions");
    for (const decision of data.decisions) {
      const row = el("div", "drow");
      row.appendChild(el("span", decision.selected ? "ok" : "no", decision.selected ? "✓" : "✕"));
      row.appendChild(el("span", null, decision.memory_id));
      row.appendChild(el("span", "no", decision.reason.join(", ")));
      decisions.appendChild(row);
    }
    out.appendChild(decisions);
  } catch (e) { out.textContent = ""; toast(e.message, "err"); }
});

$("btn-link").addEventListener("click", async () => {
  try {
    await api("/api/links", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({
        src_id: $("link-src").value.trim(), dst_id: $("link-dst").value.trim(),
        relation: $("link-rel").value, weight: Number($("link-weight").value),
      }),
    });
    toast("Linked.", "ok"); loadStats();
  } catch (e) { toast(e.message, "err"); }
});

$("btn-consolidate").addEventListener("click", async () => {
  const out = $("consolidate-out");
  out.textContent = "Running…";
  try {
    const result = await api("/api/consolidate", { method: "POST" });
    out.textContent = result.duplicates_merged + " duplicates merged · " + result.concepts_created + " concepts synthesized";
    loadStats();
  } catch (e) { out.textContent = ""; toast(e.message, "err"); }
});

loadStats();
</script>
</body>
</html>"""

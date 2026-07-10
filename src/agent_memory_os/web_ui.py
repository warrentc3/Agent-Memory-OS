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
  .filterrow { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .filterrow select, .filterrow input {
    padding: 8px 11px; border-radius: 9px; border: 1px solid var(--border);
    background: var(--panel); color: var(--text); font-size: 13px;
  }
  .filterrow input { width: 140px; }
  .graphwrap {
    position: relative; background: var(--panel); border: 1px solid var(--border);
    border-radius: 16px; box-shadow: var(--shadow); overflow: hidden;
  }
  #graph-canvas { display: block; width: 100%; height: 540px; cursor: grab; }
  .graphlegend {
    position: absolute; top: 12px; left: 14px; display: flex; gap: 10px; flex-wrap: wrap;
    font-size: 11.5px; color: var(--muted); pointer-events: none;
  }
  .graphlegend .key { display: flex; align-items: center; gap: 5px; }
  .graphlegend .dot { width: 9px; height: 9px; border-radius: 50%; }
  .graphtip {
    position: absolute; display: none; max-width: 320px; padding: 8px 12px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    box-shadow: var(--shadow); font-size: 12.5px; pointer-events: none; z-index: 5;
  }
  .graphhint { font-size: 12.5px; color: var(--muted); margin-top: 10px; }
  .tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 16px; }
  .tile {
    background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
    padding: 16px 18px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 2px;
  }
  .tilelabel { font-size: 12px; font-weight: 650; color: var(--muted); letter-spacing: .3px; }
  .tileval { font-size: 30px; font-weight: 750; font-variant-numeric: tabular-nums; }
  .panelgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
  .panel {
    background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
    padding: 18px; box-shadow: var(--shadow); margin-bottom: 16px;
  }
  .panelgrid .panel { margin-bottom: 0; }
  .panel h3 { margin: 0 0 14px; font-size: 13.5px; color: var(--muted); font-weight: 650; letter-spacing: .3px; }
  .hbars { display: flex; flex-direction: column; gap: 9px; }
  .hbar { display: grid; grid-template-columns: 88px 1fr 34px; align-items: center; gap: 10px; font-size: 12.5px; }
  .hbar .name { color: var(--text); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hbar .track { height: 12px; border-radius: 0 4px 4px 0; background: var(--panel-2); overflow: hidden; }
  .hbar .track i { display: block; height: 100%; border-radius: 0 4px 4px 0; background: var(--accent); }
  .hbar .val { color: var(--muted); font-variant-numeric: tabular-nums; }
  .cols { display: flex; align-items: flex-end; gap: 4px; height: 120px; padding-top: 6px; }
  .cols .col { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; height: 100%; }
  .cols .col i { display: block; background: var(--accent); border-radius: 4px 4px 0 0; min-height: 2px; }
  .cols .col span { font-size: 9.5px; color: var(--muted); text-align: center; margin-top: 5px; }
  .toplist { display: flex; flex-direction: column; gap: 9px; font-size: 13px; }
  .toplist .toprow { display: flex; gap: 10px; align-items: baseline; }
  .toplist .cnt { font-weight: 750; color: var(--accent); min-width: 30px; font-variant-numeric: tabular-nums; }
  .toplist .sm { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .editform { display: grid; gap: 10px; margin-top: 4px; }
  .editform textarea, .editform input[type=text], .editform select {
    padding: 9px 11px; border-radius: 9px; border: 1px solid var(--border);
    background: var(--panel-2); color: var(--text); font-size: 13.5px; font-family: inherit; width: 100%;
  }
  .editform textarea { min-height: 90px; resize: vertical; }
  .editform .erow { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .editform .erow > * { flex: 1; min-width: 110px; }
  @media (max-width: 720px) { .tiles, .panelgrid { grid-template-columns: 1fr 1fr; } }
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
    <button data-tab="dashboard" class="active">Dashboard</button>
    <button data-tab="search">Search</button>
    <button data-tab="browse">Browse</button>
    <button data-tab="graph">Graph</button>
    <button data-tab="add">Add memory</button>
    <button data-tab="tools">Tools</button>
  </nav>
</header>

<main>
  <section class="tab active" id="tab-dashboard">
    <div class="tiles">
      <div class="tile"><span class="tilelabel">Memories</span><span class="tileval" id="d-total">–</span></div>
      <div class="tile"><span class="tilelabel">Links</span><span class="tileval" id="d-links">–</span></div>
      <div class="tile"><span class="tilelabel">Pinned</span><span class="tileval" id="d-pinned">–</span></div>
      <div class="tile"><span class="tilelabel">Expired</span><span class="tileval" id="d-expired">–</span></div>
    </div>
    <div class="panelgrid">
      <div class="panel"><h3>By scope</h3><div class="hbars" id="d-scope"></div></div>
      <div class="panel"><h3>By type</h3><div class="hbars" id="d-type"></div></div>
    </div>
    <div class="panel"><h3>New memories · last 14 days</h3><div class="cols" id="d-activity"></div></div>
    <div class="panelgrid">
      <div class="panel"><h3>Link relations</h3><div class="hbars" id="d-relations"></div></div>
      <div class="panel"><h3>Most recalled</h3><div class="toplist" id="d-top"></div></div>
    </div>
  </section>

  <section class="tab" id="tab-search">
    <div class="searchrow">
      <input id="q" type="search" placeholder="Search memories… (associative recall included)">
      <button class="primary" id="btn-search">Search</button>
    </div>
    <div class="cards" id="search-results">
      <div class="empty"><div class="big">◈</div>Search your agent's memory.<br>Results resonate through linked memories, gated by the acting identity.</div>
    </div>
  </section>

  <section class="tab" id="tab-browse">
    <div class="filterrow">
      <select id="filter-scope">
        <option value="">all scopes</option>
        <option>user</option><option>agent</option><option>project</option>
        <option>team</option><option>global</option>
      </select>
      <select id="filter-type">
        <option value="">all types</option>
        <option>note</option><option>preference</option><option>fact</option>
        <option>procedure</option><option>environment</option><option>decision</option>
        <option>warning</option>
      </select>
      <input id="filter-owner" type="text" placeholder="owner…">
      <button class="ghost" id="btn-filter">Apply</button>
    </div>
    <div class="cards" id="browse-results"></div>
    <div class="loadmore"><button class="ghost" id="btn-more">Load more</button></div>
  </section>

  <section class="tab" id="tab-graph">
    <div class="graphwrap">
      <canvas id="graph-canvas"></canvas>
      <div class="graphlegend" id="graph-legend"></div>
      <div class="graphtip" id="graph-tip"></div>
    </div>
    <p class="graphhint">Association graph for the acting identity — an edge is shown only when both memories are visible to it. Drag nodes to untangle; click to copy a memory id.</p>
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

async function api(path, options, isRetry) {
  const request = Object.assign({}, options);
  request.headers = Object.assign({}, (options && options.headers) || {});
  const token = localStorage.getItem("amos.token");
  if (token) request.headers["Authorization"] = "Bearer " + token;
  const response = await fetch(path, request);
  if (response.status === 401 && !isRetry) {
    const supplied = prompt("This server requires an API token:");
    if (supplied) {
      localStorage.setItem("amos.token", supplied.trim());
      return api(path, options, true);
    }
  }
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
    if (button.dataset.tab === "graph") loadGraph();
    if (button.dataset.tab === "dashboard") loadDashboard();
  });
});

/* ---------- dashboard ---------- */
function hbarRow(name, value, maxValue, color) {
  const row = el("div", "hbar");
  row.appendChild(el("span", "name", name));
  const track = el("span", "track");
  const fill = el("i");
  fill.style.width = Math.max(2, Math.round((value / maxValue) * 100)) + "%";
  if (color) fill.style.background = color;
  track.appendChild(fill);
  row.appendChild(track);
  row.appendChild(el("span", "val", String(value)));
  return row;
}

function fillBars(containerId, entries, colorFor) {
  const container = $(containerId);
  container.innerHTML = "";
  const items = Object.entries(entries).sort((a, b) => b[1] - a[1]);
  if (!items.length) { container.appendChild(el("span", "sm", "—")); return; }
  const maxValue = Math.max(...items.map(([, v]) => v));
  for (const [name, value] of items) {
    container.appendChild(hbarRow(name, value, maxValue, colorFor ? colorFor(name) : null));
  }
}

async function loadDashboard() {
  let data;
  try { data = await api("/api/dashboard"); }
  catch (e) { toast(e.message, "err"); return; }
  $("d-total").textContent = data.total;
  $("d-links").textContent = data.links;
  $("d-pinned").textContent = data.pinned;
  $("d-expired").textContent = data.expired;
  fillBars("d-scope", data.by_scope, (scope) => SCOPE_COLORS[scope]);
  fillBars("d-type", data.by_type, null);
  fillBars("d-relations", data.by_relation, null);

  const activity = $("d-activity");
  activity.innerHTML = "";
  const maxCount = Math.max(...data.activity.map((d) => d.count), 1);
  for (const dayEntry of data.activity) {
    const col = el("div", "col");
    col.title = dayEntry.day + ": " + dayEntry.count;
    const bar = el("i");
    bar.style.height = Math.round((dayEntry.count / maxCount) * 92) + "%";
    if (dayEntry.count === 0) bar.style.opacity = "0.25";
    col.appendChild(bar);
    col.appendChild(el("span", null, dayEntry.day.slice(5)));
    activity.appendChild(col);
  }

  const top = $("d-top");
  top.innerHTML = "";
  if (!data.top_recalled.length) {
    top.appendChild(el("span", "sm", "No recall activity yet — feedback and auto-reinforce will populate this."));
  }
  for (const item of data.top_recalled) {
    const row = el("div", "toprow");
    row.appendChild(el("span", "cnt", "×" + item.access_count));
    row.appendChild(el("span", "sm", item.summary));
    top.appendChild(row);
  }
}

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
  const editBtn = el("button", null, "✎ Edit");
  editBtn.addEventListener("click", () => enterEditMode(card, memory));
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
  actions.append(editBtn, helpfulBtn, misleadingBtn, linksBtn, copyBtn, deleteBtn);
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

function enterEditMode(card, memory) {
  const form = el("div", "editform");
  const contentInput = el("textarea");
  contentInput.value = memory.content;
  form.appendChild(contentInput);

  const row1 = el("div", "erow");
  const scopeSelect = el("select");
  for (const scope of ["user", "agent", "project", "team", "global"]) {
    const option = el("option", null, scope);
    if (scope === memory.scope) option.selected = true;
    scopeSelect.appendChild(option);
  }
  const typeSelect = el("select");
  for (const type of ["note", "preference", "fact", "procedure", "environment", "decision", "warning"]) {
    const option = el("option", null, type);
    if (type === memory.type) option.selected = true;
    typeSelect.appendChild(option);
  }
  row1.append(scopeSelect, typeSelect);
  form.appendChild(row1);

  const tagsInput = el("input");
  tagsInput.type = "text"; tagsInput.placeholder = "tags (comma separated)";
  tagsInput.value = (memory.tags || []).join(", ");
  form.appendChild(tagsInput);

  const visibilityInput = el("input");
  visibilityInput.type = "text"; visibilityInput.placeholder = "visibility (empty = owner only)";
  visibilityInput.value = (memory.visibility || []).join(", ");
  form.appendChild(visibilityInput);

  const row2 = el("div", "erow");
  const importanceWrap = el("label", null, "imp ");
  const importanceInput = el("input"); importanceInput.type = "range";
  importanceInput.min = "0"; importanceInput.max = "1"; importanceInput.step = "0.05";
  importanceInput.value = String(memory.importance);
  importanceInput.style.accentColor = "var(--accent)";
  importanceWrap.appendChild(importanceInput);
  const confidenceWrap = el("label", null, "conf ");
  const confidenceInput = el("input"); confidenceInput.type = "range";
  confidenceInput.min = "0"; confidenceInput.max = "1"; confidenceInput.step = "0.05";
  confidenceInput.value = String(memory.confidence);
  confidenceInput.style.accentColor = "var(--accent)";
  confidenceWrap.appendChild(confidenceInput);
  const pinnedWrap = el("label", null, " 📌 pinned ");
  const pinnedInput = el("input"); pinnedInput.type = "checkbox"; pinnedInput.checked = memory.pinned;
  pinnedWrap.appendChild(pinnedInput);
  row2.append(importanceWrap, confidenceWrap, pinnedWrap);
  form.appendChild(row2);

  const row3 = el("div", "erow");
  const saveBtn = el("button", "primary", "Save");
  saveBtn.style.padding = "8px 18px";
  const cancelBtn = el("button", "ghost", "Cancel");
  row3.append(saveBtn, cancelBtn);
  form.appendChild(row3);

  saveBtn.addEventListener("click", async () => {
    try {
      const updated = await api("/api/memories/" + memory.id, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          content: contentInput.value,
          scope: scopeSelect.value,
          type: typeSelect.value,
          tags: tagsInput.value.split(",").map((t) => t.trim()).filter(Boolean),
          visibility: visibilityInput.value.split(",").map((v) => v.trim()).filter(Boolean),
          importance: Number(importanceInput.value),
          confidence: Number(confidenceInput.value),
          pinned: pinnedInput.checked,
        }),
      });
      card.replaceWith(renderCard(updated, null));
      toast("Memory updated", "ok");
    } catch (e) { toast(e.message, "err"); }
  });
  cancelBtn.addEventListener("click", () => card.replaceWith(renderCard(memory, null)));

  card.innerHTML = "";
  card.appendChild(form);
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
  if ($("filter-scope").value) params.set("scope", $("filter-scope").value);
  if ($("filter-type").value) params.set("type", $("filter-type").value);
  if ($("filter-owner").value.trim()) params.set("owner", $("filter-owner").value.trim());
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
$("btn-filter").addEventListener("click", () => refreshBrowse(false));

/* ---------- association graph ---------- */
const SCOPE_COLORS = {
  user: "#4d7fe8", agent: "#22a58c", project: "#c07f1f", team: "#d9558f", global: "#3aa653",
};
let graphState = null;

async function loadGraph() {
  const params = new URLSearchParams({ limit: "300" });
  if (actingAs()) params.set("requester_agent_id", actingAs());
  let data;
  try { data = await api("/api/graph?" + params); }
  catch (e) { toast(e.message, "err"); return; }

  const canvas = $("graph-canvas");
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = 540;
  canvas.width = width * dpr; canvas.height = height * dpr;
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);

  const legend = $("graph-legend");
  legend.innerHTML = "";
  for (const [scope, color] of Object.entries(SCOPE_COLORS)) {
    const key = el("span", "key");
    const dot = el("span", "dot"); dot.style.background = color;
    key.appendChild(dot); key.appendChild(el("span", null, scope));
    legend.appendChild(key);
  }

  if (!data.nodes.length) {
    context.clearRect(0, 0, width, height);
    context.fillStyle = getComputedStyle(document.body).getPropertyValue("color");
    context.globalAlpha = 0.5; context.font = "14px sans-serif"; context.textAlign = "center";
    context.fillText("No visible links yet — link memories or let co-recall build them.", width / 2, height / 2);
    context.globalAlpha = 1;
    graphState = null;
    return;
  }

  const nodes = data.nodes.map((n, i) => ({
    ...n,
    x: width / 2 + Math.cos(i * 2.399) * (60 + 10 * i % 200),
    y: height / 2 + Math.sin(i * 2.399) * (60 + 7 * i % 160),
    vx: 0, vy: 0, r: 6 + Math.min(10, n.degree * 1.6),
  }));
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const edges = data.edges.map((e) => ({ ...e, a: byId[e.src], b: byId[e.dst] }));
  graphState = { nodes: nodes, edges: edges, ctx: context, w: width, h: height, frame: 0, drag: null, hover: null };
  requestAnimationFrame(stepGraph);
}

function stepGraph() {
  const g = graphState;
  if (!g) return;
  const settled = g.frame > 300;
  if (!settled || g.drag) {
    for (let i = 0; i < g.nodes.length; i++) {
      const a = g.nodes[i];
      for (let j = i + 1; j < g.nodes.length; j++) {
        const b = g.nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y;
        let d2 = dx * dx + dy * dy || 1;
        const force = Math.min(1600 / d2, 4);
        const d = Math.sqrt(d2);
        dx /= d; dy /= d;
        a.vx += dx * force; a.vy += dy * force;
        b.vx -= dx * force; b.vy -= dy * force;
      }
      a.vx += (g.w / 2 - a.x) * 0.002;
      a.vy += (g.h / 2 - a.y) * 0.002;
    }
    for (const edge of g.edges) {
      const dx = edge.b.x - edge.a.x, dy = edge.b.y - edge.a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const pull = (d - 110) * 0.004 * (0.4 + edge.weight);
      edge.a.vx += (dx / d) * pull; edge.a.vy += (dy / d) * pull;
      edge.b.vx -= (dx / d) * pull; edge.b.vy -= (dy / d) * pull;
    }
    for (const node of g.nodes) {
      if (g.drag && g.drag.node === node) { node.vx = 0; node.vy = 0; continue; }
      node.vx *= 0.82; node.vy *= 0.82;
      node.x = Math.max(node.r, Math.min(g.w - node.r, node.x + node.vx));
      node.y = Math.max(node.r, Math.min(g.h - node.r, node.y + node.vy));
    }
  }
  drawGraph();
  g.frame += 1;
  requestAnimationFrame(stepGraph);
}

function drawGraph() {
  const g = graphState;
  if (!g) return;
  const context = g.ctx;
  context.clearRect(0, 0, g.w, g.h);
  for (const edge of g.edges) {
    const highlighted = g.hover && (edge.a === g.hover || edge.b === g.hover);
    context.strokeStyle = highlighted ? "#9a7bff" : "rgba(128,136,168,.35)";
    context.lineWidth = 0.6 + edge.weight * 2.4;
    context.setLineDash(edge.relation === "supersedes" ? [5, 4] : []);
    context.beginPath();
    context.moveTo(edge.a.x, edge.a.y);
    context.lineTo(edge.b.x, edge.b.y);
    context.stroke();
  }
  context.setLineDash([]);
  for (const node of g.nodes) {
    context.beginPath();
    context.arc(node.x, node.y, node.r, 0, Math.PI * 2);
    context.fillStyle = SCOPE_COLORS[node.scope] || "#888";
    context.globalAlpha = g.hover && g.hover !== node ? 0.45 : 1;
    context.fill();
    context.globalAlpha = 1;
    if (node.pinned) {
      context.strokeStyle = "#ffffff";
      context.lineWidth = 1.6;
      context.stroke();
    }
  }
}

(function wireGraphPointer() {
  const canvas = $("graph-canvas");
  const tip = $("graph-tip");
  const findNode = (event) => {
    if (!graphState) return null;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    return graphState.nodes.find((n) => (n.x - x) ** 2 + (n.y - y) ** 2 <= (n.r + 4) ** 2) || null;
  };
  canvas.addEventListener("mousemove", (event) => {
    if (!graphState) return;
    const rect = canvas.getBoundingClientRect();
    if (graphState.drag) {
      graphState.drag.moved = true;
      graphState.drag.node.x = event.clientX - rect.left;
      graphState.drag.node.y = event.clientY - rect.top;
      return;
    }
    const node = findNode(event);
    graphState.hover = node;
    canvas.style.cursor = node ? "pointer" : "grab";
    if (node) {
      tip.style.display = "block";
      tip.style.left = Math.min(node.x + 14, graphState.w - 330) + "px";
      tip.style.top = (node.y + 14) + "px";
      tip.textContent = node.scope + "/" + node.type + " · " + node.degree + " links — " + node.label;
    } else {
      tip.style.display = "none";
    }
  });
  canvas.addEventListener("mousedown", (event) => {
    const node = findNode(event);
    if (node) graphState.drag = { node: node, moved: false };
  });
  canvas.addEventListener("mouseup", (event) => {
    if (!graphState) return;
    if (graphState.drag && !graphState.drag.moved) {
      const node = findNode(event);
      if (node) { navigator.clipboard.writeText(node.id); toast("Copied " + node.id, "ok"); }
    }
    if (graphState.drag) graphState.drag = null;
  });
  canvas.addEventListener("mouseleave", () => {
    if (graphState) { graphState.hover = null; graphState.drag = null; }
    tip.style.display = "none";
  });
})();

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
loadDashboard();
</script>
</body>
</html>"""

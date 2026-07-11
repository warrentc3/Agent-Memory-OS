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
<link rel="icon" type="image/png" href="data:image/png;base64,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">
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
  .brand .logo { width: 32px; height: 32px; display: block; }
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
  .badge.kind-claude-code { background: #3a2218; color: #e8977a; }
  .badge.kind-codex       { background: #22282a; color: #c7d3d0; }
  .badge.kind-openclaw    { background: #3a1a12; color: #f08a68; }
  .badge.kind-hermes      { background: #241d4e; color: #a897f0; }
  .badge.kind-custom      { background: var(--panel-2); color: var(--muted); }
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
  .tool.danger { border-color: color-mix(in srgb, var(--bad) 45%, var(--border)); }
  .tool.danger h3 { color: var(--bad); }
  button.dangerbtn { color: var(--bad); border-color: color-mix(in srgb, var(--bad) 55%, var(--border)); flex: 0 0 auto; }
  button.dangerbtn:hover { background: var(--bad); border-color: var(--bad); color: #fff; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-bottom: 16px; }
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
  .healthrow { display: flex; gap: 24px; flex-wrap: wrap; font-size: 13px; }
  .healthstat { display: flex; flex-direction: column; gap: 2px; }
  .healthstat b { font-size: 20px; font-variant-numeric: tabular-nums; }
  .healthstat span { color: var(--muted); font-size: 11.5px; }
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
    <div class="brand"><img class="logo" src="data:image/png;base64,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" alt=""> AgentMemoryOS <span style="font-weight:400;color:var(--muted);font-size:13px">Web UI</span><span id="node-name" style="font-weight:400;color:var(--muted);font-size:12px;margin-left:6px"></span></div>
    <div class="stats">
      <span class="chip">Total memories <b id="stat-total">–</b></span>
      <span class="chip">Links <b id="stat-links">–</b></span>
    </div>
    <div class="acting">
      <span title="Requester identity used for search, context packs and feedback. Empty = unrestricted admin view.">Acting as</span>
      <input id="acting-as" type="text" placeholder="admin (all)" autocomplete="off" list="agent-ids">
      <datalist id="agent-ids"></datalist>
    </div>
  </div>
  <nav class="tabs">
    <button data-tab="dashboard" class="active">Dashboard</button>
    <button data-tab="search">Search</button>
    <button data-tab="browse">Browse</button>
    <button data-tab="graph">Graph</button>
    <button data-tab="agents">Agents</button>
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
      <div class="tile"><span class="tilelabel">Archived</span><span class="tileval" id="d-archived">–</span></div>
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
    <div class="panel"><h3>Resonance health</h3>
      <div class="healthrow" id="d-health"></div>
      <div class="toplist" id="d-hubs" style="margin-top:12px"></div>
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

  <section class="tab" id="tab-agents">
    <div class="panel">
      <h3>Register / update an agent</h3>
      <p class="hint" style="font-size:12.5px;color:var(--muted);margin:0 0 12px">One project can mix Claude Code, Codex, OpenClaw, and multiple Hermes profiles against this store. Register each with its teams — team members automatically see <code>team:&lt;id&gt;</code> memories, and MCP servers declare identity via <code>AGENT_MEMORY_AGENT_ID</code>.</p>
      <div class="filterrow">
        <input id="ag-id" type="text" placeholder="agent id (e.g. neo)">
        <input id="ag-name" type="text" placeholder="display name">
        <select id="ag-kind">
          <option>claude-code</option><option>codex</option><option>openclaw</option>
          <option>hermes</option><option selected>custom</option>
        </select>
        <input id="ag-teams" type="text" placeholder="teams, comma separated (= projects)">
        <button class="ghost" id="btn-agent-save">Save agent</button>
      </div>
    </div>
    <div class="cards" id="agents-list"></div>
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
      <div class="tool" style="grid-column: 1 / -1;">
        <h3>Orchestrated context <span style="font-weight:400;color:var(--muted);font-size:12px">(budget-aware, v0.4)</span></h3>
        <p class="hint">One call, five buckets: session snapshot pointer, bedrock constants, proactive warnings and procedures, then relevance recall. With a session id, repeated calls skip what was already delivered.</p>
        <div class="row">
          <input id="orch-task" type="text" placeholder="Task description">
          <input id="orch-session" type="text" placeholder="session id (optional)" style="max-width:170px">
          <input id="orch-tokens" type="number" value="2000" min="128" max="32000" style="max-width:100px">
          <button class="ghost" id="btn-orchestrate">Orchestrate</button>
        </div>
        <div id="orch-out"></div>
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
      <div class="tool" style="grid-column: 1 / -1;">
        <h3>Retention &amp; archive</h3>
        <p class="hint">Move expired memories into the cold archive (out of recall, restorable). Optionally also archive unpinned memories idle beyond N decay half-lives.</p>
        <div class="row">
          <button class="ghost" id="btn-retention">Archive expired</button>
          <input id="retention-halflives" type="number" min="1" step="0.5" value="4" style="max-width:90px" title="decay half-lives">
          <button class="ghost" id="btn-retention-decay">Also archive decayed</button>
        </div>
        <div id="retention-out" style="margin:6px 0;font-size:13px;color:var(--muted)"></div>
        <div class="toplist" id="archive-list"></div>
      </div>
      <div class="tool" style="grid-column: 1 / -1;">
        <h3>Federation</h3>
        <p class="hint">Move memories between hosts. Download this host's bundle, or import a bundle exported elsewhere — memories and profiles merge last-writer-wins, links keep their strongest form.</p>
        <div class="row">
          <button class="ghost" id="btn-bundle-export">⬇ Download bundle</button>
          <input type="file" id="bundle-file" accept=".jsonl" style="flex:1;min-width:160px">
          <button class="ghost" id="btn-bundle-import">⬆ Import bundle</button>
        </div>
        <div id="sync-out" style="margin-top:6px;font-size:13px;color:var(--muted)"></div>
        <div class="row" style="margin-top:12px">
          <input id="peer-url" type="text" placeholder="peer url, e.g. http://host:8000">
          <input id="peer-token" type="password" placeholder="peer token (optional)" style="max-width:180px">
          <input id="peer-name" type="text" placeholder="peer name (optional)" style="max-width:150px">
          <select id="peer-policy" title="what to sync to this peer" style="max-width:200px">
            <option value="shared">shared (no private)</option>
            <option value="full">full (all — trusted node)</option>
          </select>
          <button class="ghost" id="btn-peer-add">Add peer</button>
          <button class="ghost" id="btn-sync-now">⇆ Sync mesh now</button>
        </div>
        <div class="toplist" id="peer-list" style="margin-top:8px"></div>
      </div>
      <div class="tool danger" style="grid-column: 1 / -1;">
        <h3>⚠ Danger zone — forget an agent</h3>
        <p class="hint">Permanently deletes EVERY memory owned by the agent id, all links touching them, and its recall profile. This cannot be undone.</p>
        <div class="row">
          <input id="purge-owner" type="text" placeholder="agent / owner id (e.g. mizuki)">
          <button class="ghost dangerbtn" id="btn-purge">Delete all memories</button>
        </div>
        <div id="purge-out" style="margin-top:6px;font-size:13px;color:var(--muted)"></div>
      </div>
    </div>
  </section>
</main>

<div id="toasts"></div>

<div id="login-overlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:9999;align-items:center;justify-content:center">
  <div style="background:var(--card,#1b1e2e);border:1px solid var(--border,#2a2f45);padding:22px 24px;border-radius:14px;width:min(420px,90vw);box-shadow:0 12px 40px rgba(0,0,0,.5)">
    <div style="font-weight:700;font-size:16px;margin-bottom:6px">API token required</div>
    <div style="color:var(--muted,#8b93b0);font-size:13px;margin-bottom:14px">Paste the token shown by <code>agent-memory token show</code>.</div>
    <input id="login-token" type="password" placeholder="amos_\u2026" autocomplete="off" style="width:100%;box-sizing:border-box;margin-bottom:12px">
    <div style="display:flex;align-items:center;gap:10px">
      <button class="ghost" id="login-connect">Connect</button>
      <span id="login-err" style="color:#e0555f;font-size:13px"></span>
    </div>
  </div>
</div>

<script>
"use strict";
const $ = (id) => document.getElementById(id);

/* ---------- i18n ---------- */
const LOCALES = { "en": "English", "zh-TW": "繁體中文", "zh-CN": "简体中文", "ja": "日本語", "ko": "한국어" };
const I18N = {
"zh-TW": {
"Dashboard":"儀表板","Search":"搜尋","Browse":"瀏覽","Graph":"圖譜","Agents":"代理","Add memory":"新增記憶","Tools":"工具",
"Acting as":"目前身分","admin (all)":"管理者(全部)","Total memories":"記憶總數","Links":"關聯",
"Memories":"記憶","Pinned":"釘選","Expired":"已過期","Archived":"已歸檔",
"By scope":"依範圍","By type":"依類型","New memories · last 14 days":"新增記憶 · 近 14 天","Link relations":"關聯類型","Most recalled":"最常被回想","Resonance health":"共鳴健康度",
"linked memories":"有關聯的記憶","orphans (no links)":"孤立(無關聯)","avg links / memory":"平均關聯數","stale links (90d+)":"陳舊關聯(90天+)","Strongest hubs:":"最強樞紐:",
"No recall activity yet — feedback and auto-reinforce will populate this.":"尚無回想活動——回饋與自動強化會填入此處。",
"Search memories… (associative recall included)":"搜尋記憶……(含聯想回想)",
"Search your agent's memory.":"搜尋你的代理的記憶。","Results resonate through linked memories, gated by the acting identity.":"結果會沿關聯記憶共鳴浮現,並受目前身分的權限管控。",
"Searching…":"搜尋中……","Nothing recalled for that query":"沒有回想起相關記憶",
"all scopes":"全部範圍","all types":"全部類型","owner…":"擁有者……","Apply":"套用","Load more":"載入更多","No memories yet. Add the first one.":"還沒有記憶,新增第一筆吧。",
"Association graph for the acting identity — an edge is shown only when both memories are visible to it. Drag nodes to untangle; click to copy a memory id.":"目前身分的關聯圖——僅當兩端記憶皆可見時才顯示邊。拖曳節點整理佈局;點擊複製記憶 ID。",
"Register / update an agent":"註冊/更新代理","Save agent":"儲存代理","agent id (e.g. neo)":"代理 ID(例:neo)","display name":"顯示名稱","teams, comma separated (= projects)":"團隊,逗號分隔(=專案)",
"No agents registered yet.":"尚未註冊任何代理。","no teams":"無團隊","never seen":"從未活動","👤 Act as":"👤 切換身分","🗑 Remove":"🗑 移除","memories":"筆記憶",
"One project can mix Claude Code, Codex, OpenClaw, and multiple Hermes profiles against this store. Register each with its teams — team members automatically see team:<id> memories, and MCP servers declare identity via AGENT_MEMORY_AGENT_ID.":"一個專案可混用 Claude Code、Codex、OpenClaw 與多個 Hermes profiles。為每個代理註冊所屬團隊——成員自動可見 team:<id> 記憶;MCP 伺服器以 AGENT_MEMORY_AGENT_ID 宣告身分。",
"Content":"內容","Owner":"擁有者","Scope":"範圍","Type":"類型","Tags":"標籤","Visibility":"可見性","Importance":"重要性","Confidence":"信心度","Expires at":"過期時間","Save memory":"儲存記憶",
"What should be remembered?":"要記住什麼?","owner only":"僅擁有者","Pinned":"釘選","Auto-link similar":"自動關聯相似記憶",
"Context pack preview":"Context Pack 預覽","Build pack":"產生 Pack","Query":"查詢","auto-reinforce":"自動強化",
"Orchestrated context":"編排式 Context","Orchestrate":"編排","Task description":"任務描述","session id (optional)":"session ID(選填)",
"Link two memories":"連結兩筆記憶","Link":"建立關聯","src memory id":"來源記憶 ID","dst memory id":"目標記憶 ID",
"Consolidate":"整併","Run consolidation":"執行整併",
"Retention & archive":"保留策略與歸檔","Archive expired":"歸檔過期記憶","Also archive decayed":"連同深度衰減","Archive is empty.":"歸檔是空的。","restore":"還原",
"Federation":"聯邦同步","⬇ Download bundle":"⬇ 下載 Bundle","⬆ Import bundle":"⬆ 匯入 Bundle","Add peer":"加入節點","⇆ Sync mesh now":"⇆ 立即同步網格","peer url, e.g. http://host:8000":"節點網址,例:http://host:8000","peer token (optional)":"節點 token(選填)","peer name (optional)":"節點名稱(選填)","Graph unavailable.":"圖譜暫時無法載入。","No peers registered — this host syncs alone.":"尚未註冊任何節點——本機獨立運作。","remove":"移除","full policy shares private memories — use only for your own trusted nodes":"full 政策會外傳私有記憶——僅用於你自己的信任節點",
"⚠ Danger zone — forget an agent":"⚠ 危險區——遺忘一個代理","Delete all memories":"刪除全部記憶","agent / owner id (e.g. mizuki)":"代理/擁有者 ID(例:mizuki)",
"✎ Edit":"✎ 編輯","👍 Helpful":"👍 有幫助","👎 Misleading":"👎 誤導","🔗 Links":"🔗 關聯","⇢ Share":"⇢ 分享","⧉ Copy id":"⧉ 複製 ID","🗑 Delete":"🗑 刪除","why?":"為什麼?","Save":"儲存","Cancel":"取消","No links yet.":"尚無關聯。","Loading…":"載入中……","Ready.":"就緒。","🔒 private":"🔒 私有"
},
"zh-CN": {
"Dashboard":"仪表板","Search":"搜索","Browse":"浏览","Graph":"图谱","Agents":"代理","Add memory":"新增记忆","Tools":"工具",
"Acting as":"当前身份","admin (all)":"管理员(全部)","Total memories":"记忆总数","Links":"关联",
"Memories":"记忆","Pinned":"置顶","Expired":"已过期","Archived":"已归档",
"By scope":"按范围","By type":"按类型","New memories · last 14 days":"新增记忆 · 近 14 天","Link relations":"关联类型","Most recalled":"最常被回想","Resonance health":"共鸣健康度",
"linked memories":"有关联的记忆","orphans (no links)":"孤立(无关联)","avg links / memory":"平均关联数","stale links (90d+)":"陈旧关联(90天+)","Strongest hubs:":"最强枢纽:",
"No recall activity yet — feedback and auto-reinforce will populate this.":"尚无回想活动——反馈与自动强化会填充此处。",
"Search memories… (associative recall included)":"搜索记忆……(含联想回想)",
"Search your agent's memory.":"搜索你的代理的记忆。","Results resonate through linked memories, gated by the acting identity.":"结果会沿关联记忆共鸣浮现,并受当前身份的权限管控。",
"Searching…":"搜索中……","Nothing recalled for that query":"没有回想起相关记忆",
"all scopes":"全部范围","all types":"全部类型","owner…":"所有者……","Apply":"应用","Load more":"加载更多","No memories yet. Add the first one.":"还没有记忆,添加第一条吧。",
"Association graph for the acting identity — an edge is shown only when both memories are visible to it. Drag nodes to untangle; click to copy a memory id.":"当前身份的关联图——仅当两端记忆均可见时才显示边。拖拽节点整理布局;点击复制记忆 ID。",
"Register / update an agent":"注册/更新代理","Save agent":"保存代理","agent id (e.g. neo)":"代理 ID(如:neo)","display name":"显示名称","teams, comma separated (= projects)":"团队,逗号分隔(=项目)",
"No agents registered yet.":"尚未注册任何代理。","no teams":"无团队","never seen":"从未活动","👤 Act as":"👤 切换身份","🗑 Remove":"🗑 移除","memories":"条记忆",
"One project can mix Claude Code, Codex, OpenClaw, and multiple Hermes profiles against this store. Register each with its teams — team members automatically see team:<id> memories, and MCP servers declare identity via AGENT_MEMORY_AGENT_ID.":"一个项目可混用 Claude Code、Codex、OpenClaw 与多个 Hermes profiles。为每个代理注册所属团队——成员自动可见 team:<id> 记忆;MCP 服务器以 AGENT_MEMORY_AGENT_ID 声明身份。",
"Content":"内容","Owner":"所有者","Scope":"范围","Type":"类型","Tags":"标签","Visibility":"可见性","Importance":"重要性","Confidence":"置信度","Expires at":"过期时间","Save memory":"保存记忆",
"What should be remembered?":"要记住什么?","owner only":"仅所有者","Auto-link similar":"自动关联相似记忆",
"Context pack preview":"Context Pack 预览","Build pack":"生成 Pack","Query":"查询","auto-reinforce":"自动强化",
"Orchestrated context":"编排式 Context","Orchestrate":"编排","Task description":"任务描述","session id (optional)":"session ID(可选)",
"Link two memories":"连接两条记忆","Link":"建立关联","src memory id":"源记忆 ID","dst memory id":"目标记忆 ID",
"Consolidate":"整并","Run consolidation":"执行整并",
"Retention & archive":"保留策略与归档","Archive expired":"归档过期记忆","Also archive decayed":"连同深度衰减","Archive is empty.":"归档是空的。","restore":"恢复",
"Federation":"联邦同步","⬇ Download bundle":"⬇ 下载 Bundle","⬆ Import bundle":"⬆ 导入 Bundle","Add peer":"添加节点","⇆ Sync mesh now":"⇆ 立即同步网格","peer url, e.g. http://host:8000":"节点地址,如:http://host:8000","peer token (optional)":"节点 token(可选)","peer name (optional)":"节点名称(可选)","Graph unavailable.":"图谱暂时无法加载。","No peers registered — this host syncs alone.":"尚未注册任何节点——本机独立运行。","remove":"移除","full policy shares private memories — use only for your own trusted nodes":"full 策略会外传私有记忆——仅用于你自己的信任节点",
"⚠ Danger zone — forget an agent":"⚠ 危险区——遗忘一个代理","Delete all memories":"删除全部记忆","agent / owner id (e.g. mizuki)":"代理/所有者 ID(如:mizuki)",
"✎ Edit":"✎ 编辑","👍 Helpful":"👍 有帮助","👎 Misleading":"👎 误导","🔗 Links":"🔗 关联","⇢ Share":"⇢ 分享","⧉ Copy id":"⧉ 复制 ID","🗑 Delete":"🗑 删除","why?":"为什么?","Save":"保存","Cancel":"取消","No links yet.":"暂无关联。","Loading…":"加载中……","Ready.":"就绪。","🔒 private":"🔒 私有"
},
"ja": {
"Dashboard":"ダッシュボード","Search":"検索","Browse":"一覧","Graph":"グラフ","Agents":"エージェント","Add memory":"記憶を追加","Tools":"ツール",
"Acting as":"操作中の身元","admin (all)":"管理者(すべて)","Total memories":"記憶総数","Links":"リンク",
"Memories":"記憶","Pinned":"ピン留め","Expired":"期限切れ","Archived":"アーカイブ済み",
"By scope":"スコープ別","By type":"タイプ別","New memories · last 14 days":"新規記憶 · 過去14日","Link relations":"リンク種別","Most recalled":"最も想起された記憶","Resonance health":"共鳴ヘルス",
"linked memories":"リンク済み記憶","orphans (no links)":"孤立(リンクなし)","avg links / memory":"平均リンク数","stale links (90d+)":"古いリンク(90日+)","Strongest hubs:":"最強ハブ:",
"No recall activity yet — feedback and auto-reinforce will populate this.":"まだ想起履歴がありません——フィードバックと自動強化でここに表示されます。",
"Search memories… (associative recall included)":"記憶を検索……(連想想起を含む)",
"Search your agent's memory.":"エージェントの記憶を検索。","Results resonate through linked memories, gated by the acting identity.":"結果はリンクされた記憶を通じて共鳴し、操作中の身元の権限で制御されます。",
"Searching…":"検索中……","Nothing recalled for that query":"該当する記憶は想起されませんでした",
"all scopes":"すべてのスコープ","all types":"すべてのタイプ","owner…":"所有者……","Apply":"適用","Load more":"さらに読み込む","No memories yet. Add the first one.":"まだ記憶がありません。最初の一件を追加しましょう。",
"Association graph for the acting identity — an edge is shown only when both memories are visible to it. Drag nodes to untangle; click to copy a memory id.":"操作中の身元の関連グラフ——両端の記憶が可視の場合のみエッジを表示。ノードをドラッグで整理、クリックで記憶IDをコピー。",
"Register / update an agent":"エージェントの登録/更新","Save agent":"エージェントを保存","agent id (e.g. neo)":"エージェントID(例:neo)","display name":"表示名","teams, comma separated (= projects)":"チーム、カンマ区切り(=プロジェクト)",
"No agents registered yet.":"登録されたエージェントはまだありません。","no teams":"チームなし","never seen":"活動記録なし","👤 Act as":"👤 この身元で操作","🗑 Remove":"🗑 削除","memories":"件の記憶",
"One project can mix Claude Code, Codex, OpenClaw, and multiple Hermes profiles against this store. Register each with its teams — team members automatically see team:<id> memories, and MCP servers declare identity via AGENT_MEMORY_AGENT_ID.":"一つのプロジェクトで Claude Code・Codex・OpenClaw・複数の Hermes プロファイルを併用できます。各エージェントをチームと共に登録——メンバーは team:<id> の記憶を自動的に閲覧でき、MCP サーバーは AGENT_MEMORY_AGENT_ID で身元を宣言します。",
"Content":"内容","Owner":"所有者","Scope":"スコープ","Type":"タイプ","Tags":"タグ","Visibility":"可視性","Importance":"重要度","Confidence":"確信度","Expires at":"有効期限","Save memory":"記憶を保存",
"What should be remembered?":"何を記憶しますか?","owner only":"所有者のみ","Auto-link similar":"類似記憶を自動リンク",
"Context pack preview":"コンテキストパックのプレビュー","Build pack":"パック生成","Query":"クエリ","auto-reinforce":"自動強化",
"Orchestrated context":"オーケストレーテッド・コンテキスト","Orchestrate":"編成","Task description":"タスクの説明","session id (optional)":"セッションID(任意)",
"Link two memories":"記憶をリンク","Link":"リンク","src memory id":"元の記憶ID","dst memory id":"先の記憶ID",
"Consolidate":"統合","Run consolidation":"統合を実行",
"Retention & archive":"保持とアーカイブ","Archive expired":"期限切れをアーカイブ","Also archive decayed":"減衰分も含める","Archive is empty.":"アーカイブは空です。","restore":"復元",
"Federation":"フェデレーション","⬇ Download bundle":"⬇ バンドルをダウンロード","⬆ Import bundle":"⬆ バンドルをインポート","Add peer":"ピアを追加","⇆ Sync mesh now":"⇆ 今すぐメッシュ同期","peer url, e.g. http://host:8000":"ピアURL(例:http://host:8000)","peer token (optional)":"ピアトークン(任意)","peer name (optional)":"ピア名(任意)","Graph unavailable.":"グラフを読み込めません。","No peers registered — this host syncs alone.":"ピア未登録——このホストは単独で動作します。","remove":"削除","full policy shares private memories — use only for your own trusted nodes":"fullポリシーはプライベート記憶も送信します——自分の信頼できるノードのみに使用してください",
"⚠ Danger zone — forget an agent":"⚠ 危険ゾーン——エージェントを忘却","Delete all memories":"全記憶を削除","agent / owner id (e.g. mizuki)":"エージェント/所有者ID(例:mizuki)",
"✎ Edit":"✎ 編集","👍 Helpful":"👍 役立った","👎 Misleading":"👎 誤解を招く","🔗 Links":"🔗 リンク","⇢ Share":"⇢ 共有","⧉ Copy id":"⧉ IDコピー","🗑 Delete":"🗑 削除","why?":"理由は?","Save":"保存","Cancel":"キャンセル","No links yet.":"リンクはまだありません。","Loading…":"読み込み中……","Ready.":"準備完了。","🔒 private":"🔒 プライベート"
},
"ko": {
"Dashboard":"대시보드","Search":"검색","Browse":"둘러보기","Graph":"그래프","Agents":"에이전트","Add memory":"기억 추가","Tools":"도구",
"Acting as":"현재 신원","admin (all)":"관리자(전체)","Total memories":"기억 총수","Links":"연결",
"Memories":"기억","Pinned":"고정됨","Expired":"만료됨","Archived":"보관됨",
"By scope":"범위별","By type":"유형별","New memories · last 14 days":"신규 기억 · 최근 14일","Link relations":"연결 유형","Most recalled":"가장 많이 회상됨","Resonance health":"공명 상태",
"linked memories":"연결된 기억","orphans (no links)":"고립(연결 없음)","avg links / memory":"평균 연결 수","stale links (90d+)":"오래된 연결(90일+)","Strongest hubs:":"최강 허브:",
"No recall activity yet — feedback and auto-reinforce will populate this.":"아직 회상 활동이 없습니다 — 피드백과 자동 강화로 채워집니다.",
"Search memories… (associative recall included)":"기억 검색…(연상 회상 포함)",
"Search your agent's memory.":"에이전트의 기억을 검색하세요.","Results resonate through linked memories, gated by the acting identity.":"결과는 연결된 기억을 통해 공명하며, 현재 신원의 권한으로 제어됩니다.",
"Searching…":"검색 중……","Nothing recalled for that query":"해당 쿼리로 회상된 기억이 없습니다",
"all scopes":"모든 범위","all types":"모든 유형","owner…":"소유자……","Apply":"적용","Load more":"더 불러오기","No memories yet. Add the first one.":"아직 기억이 없습니다. 첫 기억을 추가하세요.",
"Association graph for the acting identity — an edge is shown only when both memories are visible to it. Drag nodes to untangle; click to copy a memory id.":"현재 신원의 연관 그래프 — 양쪽 기억이 모두 보일 때만 엣지가 표시됩니다. 노드를 드래그해 정리하고, 클릭하면 기억 ID가 복사됩니다.",
"Register / update an agent":"에이전트 등록/수정","Save agent":"에이전트 저장","agent id (e.g. neo)":"에이전트 ID(예: neo)","display name":"표시 이름","teams, comma separated (= projects)":"팀, 쉼표로 구분(=프로젝트)",
"No agents registered yet.":"등록된 에이전트가 없습니다.","no teams":"팀 없음","never seen":"활동 기록 없음","👤 Act as":"👤 이 신원으로 전환","🗑 Remove":"🗑 제거","memories":"개의 기억",
"One project can mix Claude Code, Codex, OpenClaw, and multiple Hermes profiles against this store. Register each with its teams — team members automatically see team:<id> memories, and MCP servers declare identity via AGENT_MEMORY_AGENT_ID.":"하나의 프로젝트에서 Claude Code, Codex, OpenClaw, 여러 Hermes 프로필을 함께 사용할 수 있습니다. 각 에이전트를 팀과 함께 등록하세요 — 팀원은 team:<id> 기억을 자동으로 볼 수 있고, MCP 서버는 AGENT_MEMORY_AGENT_ID로 신원을 선언합니다.",
"Content":"내용","Owner":"소유자","Scope":"범위","Type":"유형","Tags":"태그","Visibility":"공개 범위","Importance":"중요도","Confidence":"신뢰도","Expires at":"만료 시각","Save memory":"기억 저장",
"What should be remembered?":"무엇을 기억할까요?","owner only":"소유자 전용","Auto-link similar":"유사 기억 자동 연결",
"Context pack preview":"컨텍스트 팩 미리보기","Build pack":"팩 생성","Query":"쿼리","auto-reinforce":"자동 강화",
"Orchestrated context":"오케스트레이션 컨텍스트","Orchestrate":"오케스트레이션","Task description":"작업 설명","session id (optional)":"세션 ID(선택)",
"Link two memories":"기억 두 개 연결","Link":"연결","src memory id":"원본 기억 ID","dst memory id":"대상 기억 ID",
"Consolidate":"통합","Run consolidation":"통합 실행",
"Retention & archive":"보존 및 보관","Archive expired":"만료 기억 보관","Also archive decayed":"감쇠 기억도 포함","Archive is empty.":"보관함이 비어 있습니다.","restore":"복원",
"Federation":"페더레이션","⬇ Download bundle":"⬇ 번들 다운로드","⬆ Import bundle":"⬆ 번들 가져오기","Add peer":"피어 추가","⇆ Sync mesh now":"⇆ 지금 메시 동기화","peer url, e.g. http://host:8000":"피어 URL, 예: http://host:8000","peer token (optional)":"피어 토큰(선택)","peer name (optional)":"피어 이름(선택)","Graph unavailable.":"그래프를 불러올 수 없습니다.","No peers registered — this host syncs alone.":"등록된 피어가 없습니다 — 이 호스트는 단독으로 동작합니다.","remove":"제거","full policy shares private memories — use only for your own trusted nodes":"full 정책은 비공개 기억까지 전송합니다 — 신뢰하는 자체 노드에만 사용하세요",
"⚠ Danger zone — forget an agent":"⚠ 위험 구역 — 에이전트 망각","Delete all memories":"모든 기억 삭제","agent / owner id (e.g. mizuki)":"에이전트/소유자 ID(예: mizuki)",
"✎ Edit":"✎ 편집","👍 Helpful":"👍 도움됨","👎 Misleading":"👎 오해 유발","🔗 Links":"🔗 연결","⇢ Share":"⇢ 공유","⧉ Copy id":"⧉ ID 복사","🗑 Delete":"🗑 삭제","why?":"이유는?","Save":"저장","Cancel":"취소","No links yet.":"아직 연결이 없습니다.","Loading…":"불러오는 중……","Ready.":"준비 완료.","🔒 private":"🔒 비공개"
}
};
let locale = localStorage.getItem("amos.locale") || (() => {
  const nav = (navigator.language || "en");
  if (/^zh-(TW|HK|Hant)/i.test(nav)) return "zh-TW";
  if (/^zh/i.test(nav)) return "zh-CN";
  if (/^ja/i.test(nav)) return "ja";
  if (/^ko/i.test(nav)) return "ko";
  return "en";
})();
function t(source) {
  const dictionary = I18N[locale];
  return (dictionary && dictionary[source]) || source;
}
function applyLocale() {
  const selectors = "nav.tabs button, button, h2, .panel h3, .tool h3, .tilelabel, .hint, p.hint, .graphhint, .chip, .acting > span, .empty";
  document.querySelectorAll(selectors).forEach((node) => {
    for (const child of node.childNodes) {
      if (child.nodeType !== Node.TEXT_NODE) continue;
      const original = child.dataset === undefined
        ? (child.__i18nOriginal ?? (child.__i18nOriginal = child.nodeValue.trim()))
        : child.nodeValue.trim();
      if (original) child.nodeValue = child.nodeValue.replace(child.nodeValue.trim(), t(original));
    }
  });
  document.querySelectorAll("label.field, .checks label").forEach((node) => {
    for (const child of node.childNodes) {
      if (child.nodeType !== Node.TEXT_NODE) continue;
      const original = child.__i18nOriginal ?? (child.__i18nOriginal = child.nodeValue.trim());
      if (original) child.nodeValue = child.nodeValue.replace(child.nodeValue.trim(), t(original));
    }
  });
  document.querySelectorAll("[placeholder]").forEach((node) => {
    const original = node.dataset.i18nPh ?? (node.dataset.i18nPh = node.getAttribute("placeholder"));
    node.setAttribute("placeholder", t(original));
  });
  document.querySelectorAll('option[value=""]').forEach((option) => {
    const original = option.dataset.i18n ?? (option.dataset.i18n = option.textContent);
    option.textContent = t(original);
  });
}
(function mountLocalePicker() {
  const acting = document.querySelector(".acting");
  const picker = document.createElement("select");
  picker.id = "locale-pick";
  picker.style.cssText = "padding:6px 8px;border-radius:8px;border:1px solid var(--border);background:var(--panel);color:var(--text);font-size:12.5px";
  for (const [code, name] of Object.entries(LOCALES)) {
    const option = document.createElement("option");
    option.value = code; option.textContent = name;
    if (code === locale) option.selected = true;
    picker.appendChild(option);
  }
  picker.addEventListener("change", () => {
    locale = picker.value;
    localStorage.setItem("amos.locale", locale);
    applyLocale();
  });
  acting.appendChild(picker);
})();

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
  if (response.status === 401) {
    localStorage.removeItem("amos.token");
    showLogin(token ? t("Invalid token \u2014 please re-enter.") : "");
    throw new Error("unauthorized");
  }
  let body = null;
  try { body = await response.json(); } catch (e) { /* empty body */ }
  if (!response.ok) {
    const detail = body && (body.detail || body.error) ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body.error)) : ("HTTP " + response.status);
    throw new Error(detail);
  }
  return body;
}

function showLogin(err) {
  const o = $("login-overlay");
  if (!o) return;
  o.style.display = "flex";
  $("login-err").textContent = err || "";
  $("login-token").focus();
}
$("login-connect").addEventListener("click", () => {
  const v = $("login-token").value.trim();
  if (!v) { $("login-err").textContent = ""; return; }
  localStorage.setItem("amos.token", v);
  location.reload();
});
$("login-token").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("login-connect").click();
});

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
    if (button.dataset.tab === "agents") refreshAgents();
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
  $("d-archived").textContent = data.archived;
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
    top.appendChild(el("span", "sm", t("No recall activity yet — feedback and auto-reinforce will populate this.")));
  }
  for (const item of data.top_recalled) {
    const row = el("div", "toprow");
    row.appendChild(el("span", "cnt", "×" + item.access_count));
    row.appendChild(el("span", "sm", item.summary));
    top.appendChild(row);
  }

  const health = data.graph_health;
  const healthRow = $("d-health");
  healthRow.innerHTML = "";
  const stats = [
    [health.linked_memories, t("linked memories")],
    [health.orphan_memories, t("orphans (no links)")],
    [health.avg_degree, t("avg links / memory")],
    [health.stale_links, t("stale links (90d+)")],
  ];
  for (const [value, label] of stats) {
    const stat = el("div", "healthstat");
    stat.appendChild(el("b", null, String(value)));
    stat.appendChild(el("span", null, label));
    healthRow.appendChild(stat);
  }
  const hubs = $("d-hubs");
  hubs.innerHTML = "";
  if (health.top_hubs.length) {
    hubs.appendChild(el("span", "sm", t("Strongest hubs:")));
    for (const hub of health.top_hubs) {
      const row = el("div", "toprow");
      row.appendChild(el("span", "cnt", hub.degree + "⛓"));
      row.appendChild(el("span", "sm", hub.summary));
      hubs.appendChild(row);
    }
  }
}

/* ---------- agents ---------- */
async function refreshAgents() {
  const list = $("agents-list");
  try {
    const data = await api("/api/agents");
    const datalist = $("agent-ids");
    datalist.innerHTML = "";
    list.innerHTML = "";
    if (!data.agents.length) {
      const empty = el("div", "empty");
      empty.appendChild(el("div", "big", "🤖"));
      empty.appendChild(document.createTextNode(t("No agents registered yet.")));
      list.appendChild(empty);
      return;
    }
    for (const agent of data.agents) {
      datalist.appendChild(Object.assign(document.createElement("option"), { value: agent.id }));
      const card = el("article", "card");
      const top = el("div", "top");
      top.appendChild(el("span", "badge kind-" + agent.kind, agent.kind));
      const name = el("span", "owner");
      name.appendChild(el("b", null, agent.id));
      if (agent.display_name) name.appendChild(document.createTextNode(" · " + agent.display_name));
      top.appendChild(name);
      const meta = el("span", "scorewrap");
      meta.appendChild(el("span", "scoreval", agent.memory_count + " " + t("memories")));
      top.appendChild(meta);
      card.appendChild(top);
      const teams = el("div", "meta");
      const chips = el("span", "tags");
      for (const team of agent.teams) chips.appendChild(el("span", "tag", "team:" + team));
      if (!agent.teams.length) chips.appendChild(el("span", "sm", t("no teams")));
      teams.appendChild(chips);
      teams.appendChild(el("span", null, agent.last_seen_at ? new Date(agent.last_seen_at).toLocaleString() : t("never seen")));
      card.appendChild(teams);
      const actions = el("div", "actions");
      const actBtn = el("button", null, t("👤 Act as"));
      actBtn.addEventListener("click", () => { $("acting-as").value = agent.id; localStorage.setItem("amos.actingAs", agent.id); toast("Acting as " + agent.id, "ok"); });
      const editBtn = el("button", null, t("✎ Edit"));
      editBtn.addEventListener("click", () => {
        $("ag-id").value = agent.id; $("ag-name").value = agent.display_name;
        $("ag-kind").value = agent.kind; $("ag-teams").value = agent.teams.join(", ");
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
      const removeBtn = el("button", "danger", t("🗑 Remove"));
      removeBtn.addEventListener("click", async () => {
        if (!confirm("Unregister agent “" + agent.id + "”? Its memories stay; it loses registered team access.")) return;
        try { await api("/api/agents/" + encodeURIComponent(agent.id), { method: "DELETE" }); refreshAgents(); }
        catch (e) { toast(e.message, "err"); }
      });
      actions.append(actBtn, editBtn, removeBtn);
      card.appendChild(actions);
      list.appendChild(card);
    }
  } catch (e) { /* pre-auth */ }
}
$("btn-agent-save").addEventListener("click", async () => {
  const id = $("ag-id").value.trim();
  if (!id) { toast("Agent id is required.", "err"); return; }
  try {
    await api("/api/agents", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({
        id: id, display_name: $("ag-name").value.trim(), kind: $("ag-kind").value,
        teams: $("ag-teams").value.split(",").map(t => t.trim()).filter(Boolean),
      }) });
    toast("Agent saved.", "ok");
    $("ag-id").value = ""; $("ag-name").value = ""; $("ag-teams").value = "";
    refreshAgents();
  } catch (e) { toast(e.message, "err"); }
});
refreshAgents();

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
    top.appendChild(el("span", "owner", t("🔒 private")));
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
  const editBtn = el("button", null, t("✎ Edit"));
  editBtn.addEventListener("click", () => enterEditMode(card, memory));
  const helpfulBtn = el("button", null, t("👍 Helpful"));
  helpfulBtn.addEventListener("click", () => feedback(memory.id, true));
  const misleadingBtn = el("button", null, t("👎 Misleading"));
  misleadingBtn.addEventListener("click", () => feedback(memory.id, false));
  const linksBtn = el("button", null, t("🔗 Links"));
  const shareBtn = el("button", null, t("⇢ Share"));
  shareBtn.addEventListener("click", async () => {
    const actor = actingAs() || memory.owner;
    const target = prompt(
      "Share “" + memory.content.slice(0, 60) + "”\n\n" +
      "Grant access to (agent id, or team:<id>; prefix with ~ to share a de-identified copy):\n" +
      "Acting as owner: " + actor
    );
    if (!target) return;
    const deidentify = target.startsWith("~");
    const cleaned = deidentify ? target.slice(1).trim() : target.trim();
    const body = { actor: actor, deidentify: deidentify };
    if (cleaned.startsWith("team:")) body.to_team = cleaned.slice(5); else body.to_agent = cleaned;
    try {
      const result = await api("/api/memories/" + memory.id + "/share", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
      toast(result.deidentified
        ? "De-identified copy shared as " + result.shared_as
        : "Shared with " + result.grant + " (audited).", "ok");
    } catch (e) { toast(e.message, "err"); }
  });
  const copyBtn = el("button", null, t("⧉ Copy id"));
  copyBtn.addEventListener("click", () => { navigator.clipboard.writeText(memory.id); toast("Copied " + memory.id, "ok"); });
  const deleteBtn = el("button", "danger", t("🗑 Delete"));
  deleteBtn.addEventListener("click", async () => {
    if (!confirm("Delete this memory permanently?\n\n" + memory.content.slice(0, 120))) return;
    try {
      await api("/api/memories/" + memory.id, { method: "DELETE" });
      card.remove(); loadStats(); toast("Memory deleted", "ok");
    } catch (e) { toast(e.message, "err"); }
  });
  actions.append(editBtn, helpfulBtn, misleadingBtn, linksBtn, shareBtn, copyBtn, deleteBtn);
  if (extras && extras.reason) {
    const whyBtn = el("button", null, t("why?"));
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
      const rq = actingAs() ? "?requester_agent_id=" + encodeURIComponent(actingAs()) : "";
      const data = await api("/api/memories/" + memory.id + "/links" + rq);
      linksBox.textContent = "";
      if (!data.links.length) { linksBox.textContent = "No links yet."; return; }
      for (const link of data.links) {
        const other = link.src_id === memory.id ? link.dst_id : link.src_id;
        const row = el("div", "linkrow");
        row.appendChild(el("span", "rel", link.relation));
        const detail = await api("/api/memories/" + other + rq).catch(() => null);
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
  const saveBtn = el("button", "primary", t("Save"));
  saveBtn.style.padding = "8px 18px";
  const cancelBtn = el("button", "ghost", t("Cancel"));
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
  container.innerHTML = ""; container.appendChild(el("div", "empty", t("Searching…")));
  const params = new URLSearchParams({ q: query, limit: "20" });
  if (actingAs()) params.set("requester_agent_id", actingAs());
  try {
    const data = await api("/api/search?" + params);
    container.innerHTML = "";
    if (!data.results.length) {
      const empty = el("div", "empty");
      empty.appendChild(el("div", "big", "∅"));
      empty.appendChild(document.createTextNode(t("Nothing recalled for that query") + (actingAs() ? " — " + actingAs() : "") + "."));
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
      empty.appendChild(document.createTextNode(t("No memories yet. Add the first one.")));
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

  if (!data || !Array.isArray(data.nodes)) { toast(t("Graph unavailable."), "err"); return; }
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
  // Defensive: only keep edges whose endpoints are actually present, so a
  // stray edge can never make stepGraph read .x of undefined and freeze.
  const edges = (data.edges || [])
    .map((e) => ({ ...e, a: byId[e.src], b: byId[e.dst] }))
    .filter((e) => e.a && e.b);
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

async function refreshArchive() {
  const list = $("archive-list");
  try {
    const data = await api("/api/archive?limit=5");
    list.innerHTML = "";
    if (!data.archived.length) { list.appendChild(el("span", "sm", t("Archive is empty."))); return; }
    for (const item of data.archived) {
      const row = el("div", "toprow");
      row.appendChild(el("span", "cnt", item.archive_reason));
      row.appendChild(el("span", "sm", item.summary));
      const restoreBtn = el("button", "ghost", t("restore"));
      restoreBtn.style.cssText = "font-size:11px;padding:2px 10px;flex:0 0 auto";
      restoreBtn.addEventListener("click", async () => {
        try {
          await api("/api/archive/" + item.id + "/restore", { method: "POST" });
          toast("Restored — expiry cleared, decay clock restarted.", "ok");
          refreshArchive(); loadStats(); loadDashboard(); browseLoaded = false;
        } catch (e) { toast(e.message, "err"); }
      });
      row.appendChild(restoreBtn);
      list.appendChild(row);
    }
  } catch (e) { /* tools tab may load before auth */ }
}

async function runRetention(halfLives) {
  const out = $("retention-out");
  out.textContent = "Running…";
  try {
    const params = halfLives ? "?decayed_half_lives=" + halfLives : "";
    const result = await api("/api/retention" + params, { method: "POST" });
    out.textContent = result.archived_expired + " expired and " + result.archived_decayed + " decayed memories archived.";
    refreshArchive(); loadStats(); loadDashboard(); browseLoaded = false;
  } catch (e) { out.textContent = ""; toast(e.message, "err"); }
}
$("btn-retention").addEventListener("click", () => runRetention(null));
$("btn-retention-decay").addEventListener("click", () => runRetention($("retention-halflives").value));
refreshArchive();

$("btn-bundle-export").addEventListener("click", () => { window.location.href = "/api/sync/export"; });
$("btn-bundle-import").addEventListener("click", async () => {
  const picker = $("bundle-file");
  if (!picker.files.length) { toast("Choose a .jsonl bundle first.", "err"); return; }
  const out = $("sync-out");
  out.textContent = "Importing…";
  try {
    const body = await picker.files[0].text();
    const headers = { "content-type": "application/x-ndjson" };
    const token = localStorage.getItem("amos.token");
    if (token) headers["Authorization"] = "Bearer " + token;
    const response = await fetch("/api/sync/import", { method: "POST", headers: headers, body: body });
    const stats = await response.json();
    if (!response.ok) throw new Error(stats.detail || "import failed");
    out.textContent = "Merged: " + stats.memories_added + " added, " + stats.memories_updated +
      " updated, " + stats.memories_skipped + " skipped · links +" + stats.links_added + "/" + stats.links_merged + " merged";
    loadStats(); loadDashboard(); browseLoaded = false;
  } catch (e) { out.textContent = ""; toast(e.message, "err"); }
});

async function refreshPeers() {
  const list = $("peer-list");
  try {
    const data = await api("/api/peers");
    list.innerHTML = "";
    if (!data.peers.length) { list.appendChild(el("span", "sm", t("No peers registered — this host syncs alone."))); return; }
    for (const peer of data.peers) {
      const row = el("div", "toprow");
      const label = el("span", "sm", (peer.name ? peer.name + " · " : "") + peer.url + (peer.last_synced_at ? " · last: " + peer.last_result : " · never synced"));
      const badge = el("span", "pill", peer.policy || "shared");
      badge.style.cssText = "margin-left:6px;font-size:10px;padding:1px 7px;border-radius:8px;background:var(--chip);color:var(--muted)";
      if ((peer.policy || "shared") === "full") badge.title = t("full policy shares private memories — use only for your own trusted nodes");
      label.appendChild(badge);
      row.appendChild(label);
      const removeBtn = el("button", "ghost", t("remove"));
      removeBtn.style.cssText = "font-size:11px;padding:2px 10px;flex:0 0 auto";
      removeBtn.addEventListener("click", async () => {
        try { await api("/api/peers?url=" + encodeURIComponent(peer.url), { method: "DELETE" }); refreshPeers(); }
        catch (e) { toast(e.message, "err"); }
      });
      row.appendChild(removeBtn);
      list.appendChild(row);
    }
  } catch (e) { /* pre-auth */ }
}
$("btn-peer-add").addEventListener("click", async () => {
  const url = $("peer-url").value.trim();
  if (!url) return;
  try {
    await api("/api/peers", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ url: url, token: $("peer-token").value || null, policy: $("peer-policy").value, name: $("peer-name").value || "" }) });
    $("peer-url").value = ""; $("peer-token").value = ""; $("peer-name").value = "";
    toast("Peer registered.", "ok"); refreshPeers();
  } catch (e) { toast(e.message, "err"); }
});
$("btn-sync-now").addEventListener("click", async () => {
  const out = $("sync-out");
  out.textContent = "Syncing mesh…";
  try {
    const data = await api("/api/sync/run", { method: "POST" });
    const ok = data.results.filter(r => r.ok).length;
    out.textContent = ok + "/" + data.results.length + " peers converged.";
    refreshPeers(); loadStats(); loadDashboard(); browseLoaded = false;
  } catch (e) { out.textContent = ""; toast(e.message, "err"); }
});
async function loadNode() {
  try { const n = await api("/api/node"); $("node-name").textContent = "· " + n.node_name; }
  catch (e) { /* pre-auth */ }
}
loadNode();
refreshPeers();

$("btn-purge").addEventListener("click", async () => {
  const owner = $("purge-owner").value.trim();
  const out = $("purge-out");
  if (!owner) { toast("Enter an agent / owner id first.", "err"); return; }
  const typed = prompt(
    "This permanently deletes ALL memories, links and the recall profile of “" + owner + "”.\n\n" +
    "Type the agent id again to confirm:"
  );
  if (typed === null) return;
  if (typed.trim() !== owner) { toast("Confirmation did not match — nothing was deleted.", "err"); return; }
  try {
    const result = await api(
      "/api/owners/" + encodeURIComponent(owner) + "/memories?confirm=" + encodeURIComponent(owner),
      { method: "DELETE" }
    );
    out.textContent = result.memories_deleted + " memories and " + result.links_deleted + " links deleted for “" + owner + "”.";
    toast("Agent “" + owner + "” forgotten.", "ok");
    $("purge-owner").value = "";
    loadStats(); loadDashboard(); browseLoaded = false;
  } catch (e) { toast(e.message, "err"); }
});

$("btn-orchestrate").addEventListener("click", async () => {
  const task = $("orch-task").value.trim();
  if (!task) return;
  const params = new URLSearchParams({ task: task, max_tokens: $("orch-tokens").value });
  if ($("orch-session").value.trim()) params.set("session_id", $("orch-session").value.trim());
  if (actingAs()) params.set("requester_agent_id", actingAs());
  const out = $("orch-out");
  out.textContent = "Orchestrating…";
  try {
    const data = await api("/api/orchestrate?" + params);
    out.innerHTML = "";
    const chips = el("div", null, "");
    chips.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin:8px 0";
    chips.appendChild(Object.assign(el("span", "chip"), { textContent: data.used_tokens + " / " + data.max_tokens + " tokens" }));
    for (const [name, info] of Object.entries(data.sections)) {
      chips.appendChild(Object.assign(el("span", "chip"),
        { textContent: name + " · " + info.memory_ids.length + " · " + info.used_tokens + "t" }));
    }
    out.appendChild(chips);
    out.appendChild(el("pre", "packtext", data.text || "(empty)"));
  } catch (e) { out.textContent = ""; toast(e.message, "err"); }
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

applyLocale();
loadStats();
loadDashboard();
</script>
</body>
</html>"""

/* JobSidekick dashboard. Plain JS, no build step. Talks only to the local server it came from. */
(() => {
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const I = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>', jobs: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V4h6v3"/>',
  queue: '<path d="M4 6h16M4 12h16M4 18h10"/>', board: '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="10" rx="1"/><rect x="17" y="4" width="4" height="13" rx="1"/>',
  hand: '<path d="M7 11V5a1.5 1.5 0 013 0v5m0 0V3.5a1.5 1.5 0 013 0V10m0 0V5a1.5 1.5 0 013 0v8a7 7 0 01-7 7h-1a6 6 0 01-5-3l-2-4a1.5 1.5 0 012.5-1.5L7 14"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>', chat: '<path d="M21 12a8 8 0 01-11.5 7.2L4 20l1-4.6A8 8 0 1121 12z"/>', cog: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 00-.1-1.3l2-1.5-2-3.4-2.3 1a7 7 0 00-2.2-1.3L14 3h-4l-.4 2.5a7 7 0 00-2.2 1.3l-2.3-1-2 3.4 2 1.5A7 7 0 005 12c0 .4 0 .9.1 1.3l-2 1.5 2 3.4 2.3-1a7 7 0 002.2 1.3L10 21h4l.4-2.5a7 7 0 002.2-1.3l2.3 1 2-3.4-2-1.5c.1-.4.1-.9.1-1.3z"/>',
  term: '<path d="M4 17l6-5-6-5M12 19h8"/>', search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>', plus: '<path d="M12 5v14M5 12h14"/>', arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>', check: '<path d="M5 12l5 5 9-10"/>', grid: '<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>', filter: '<path d="M4 6h16M7 12h10M10 18h4"/>', bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>', link: '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>', file: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>', copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/>',
  sync: '<path d="M20 11a8 8 0 00-14-4L4 9M4 4v5h5M4 13a8 8 0 0014 4l2-2M20 20v-5h-5"/>', ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5"/>', cal: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
};
const ic = (n, c = '') => `<svg viewBox="0 0 24 24" class="${c}">${I[n] || ''}</svg>`;
const PAL = [['#e8f0fe', '#3b64c4'], ['#fdeee6', '#d6602a'], ['#e6f2e8', '#3a8553'], ['#f3e8fb', '#8446c4'], ['#fff4d6', '#b07d00'], ['#e0f4f4', '#1f8a8a']];
const hash = s => [...String(s)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
const avatar = name => { const [bg, fg] = PAL[hash(name) % PAL.length]; const l = (String(name).match(/[A-Za-z0-9]/) || ['?'])[0].toUpperCase(); return `<span class="av" style="background:${bg};color:${fg}">${l}</span>`; };
const HOW = { form: ['green', 'Web form'], email: ['blue', 'Email'], login: ['orange', 'Login needed'], unknown: ['gray', 'Job board'] };
const STATUS_PILL = { applied: 'green', interview: 'blue', offer: 'green', rejected: 'red', manual: 'orange', drafted: 'blue', ready: 'gray', closed: 'red', failed: 'red' };
const ago = t => { const d = (Date.now() / 1000 - t); return d < 3600 ? Math.max(1, Math.round(d / 60)) + 'm ago' : d < 86400 ? Math.round(d / 3600) + 'h ago' : Math.round(d / 86400) + 'd ago'; };
const post = (url, body) => fetch(url, { method: 'POST', headers: { 'X-Sidekick': '1', 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }).then(r => r.json());
const get = url => fetch(url).then(r => r.json());

const S = { view: 'home', tab: 'overview', jobs: [], stats: { by_status: {}, gaps: [], by_source: [], by_method: [] }, profile: {}, settings: {}, answers: [], act: null, span: 'week',
  mode: 'grid', q: '', fStatus: '', fHow: '', fScore: 0, onlyPicked: false, source: '', shown: 60, run: null, pal: null };

const NAV = [['home', 'Home', 'home'], ['jobs', 'All jobs', 'jobs'], ['queue', 'Ready to apply', 'queue'], ['pipeline', 'Pipeline', 'board'], ['manual', 'Apply by hand', 'hand'], ['insights', 'Insights', 'chart'], ['answers', 'Saved answers', 'chat']];
const TITLES = { home: 'Home', jobs: 'All jobs', queue: 'Ready to apply', pipeline: 'Pipeline', manual: 'Apply by hand', insights: 'Insights', answers: 'Saved answers', settings: 'Settings', commands: 'Commands', source: 'Source' };

/* ---------- data ---------- */
async function load(which) {
  const [jobs, stats] = await Promise.all([get('/api/jobs'), get('/api/stats')]);
  S.jobs = jobs; S.stats = stats;
  if (!which) { S.profile = await get('/api/profile'); S.settings = await get('/api/settings'); }
  S.act = await get('/api/activity?span=' + S.span);
  if (S.view === 'answers') S.answers = await get('/api/answers');
  draw();
}
const byId = id => S.jobs.find(j => j.id === id);
const picked = () => S.jobs.filter(j => j.picked);

/* ---------- pieces ---------- */
const scoreBar = n => { n = n || 0; const cls = n >= 4 ? '' : n === 3 ? 'mid' : 'low'; return `<span class="score"><span class="scorebar ${cls}">${[1, 2, 3, 4, 5].map(i => `<i class="${i <= n ? 'f' : ''}"></i>`).join('')}</span>${n ? n + '/5' : '–'}</span>`; };
const howPill = j => { const [c, t] = HOW[j.method] || HOW.unknown; return `<span class="pill ${c}">${t}</span>`; };
const stPill = st => `<span class="pill ${STATUS_PILL[st] || 'gray'}">${esc(st)}</span>`;
function card(j) {
  return `<article class="jcard ${j.picked ? 'picked' : ''}" data-open="${esc(j.id)}">
  <header>${avatar(j.company || j.title)}<div class="right"><button class="pickbox ${j.picked ? 'on' : ''}" data-pick="${esc(j.id)}" title="Pick this job to apply to">${ic('check')}</button>${howPill(j)}</div></header>
  <h3>${esc(j.title)}</h3><div class="role">${esc(j.company || '—')}</div>
  <div class="meta"><div><small>Fit score</small><b>${scoreBar(j.score)}</b></div><div><small>Found on</small><b>${esc(j.source)}</b></div></div>
  <div class="contact"><div>${esc(j.email || (j.source === 'hn' ? 'Remote (Hacker News)' : (j.location || '').slice(0, 44)) || 'Remote')}</div><div>${esc(j.salary || (j.status !== 'new' ? j.status : 'Not scored yet'))}</div></div>
  <span class="go">${ic('arrow')}</span></article>`;
}
function row(j) {
  return `<tr class="row" data-open="${esc(j.id)}"><td style="width:30px"><button class="pickbox ${j.picked ? 'on' : ''}" data-pick="${esc(j.id)}">${ic('check')}</button></td><td>${scoreBar(j.score)}</td>
  <td><div class="t">${esc(j.title)}</div><div class="s">${esc(j.company)} · ${esc((j.location || '').slice(0, 40))}</div></td><td>${howPill(j)}</td><td class="s">${esc(j.source)}</td><td>${stPill(j.status)}</td></tr>`;
}
const listOf = (js, limit) => !js.length ? `<div class="empty"><b>Nothing here yet</b>Use “Find Jobs” (or press ⌘K) to search.</div>` :
  S.mode === 'grid' ? `<div class="grid">${js.slice(0, limit).map(card).join('')}</div>` :
  `<table class="table"><thead><tr><th></th><th>Score</th><th>Job</th><th>Apply</th><th>Source</th><th>Status</th></tr></thead><tbody>${js.slice(0, limit).map(row).join('')}</tbody></table>`;
const more = (n, limit) => n > limit ? `<p style="text-align:center;margin-top:18px"><button class="btn" data-more>Show ${Math.min(60, n - limit)} more (${n - limit} left)</button></p>` : '';
function toolbar(extra = '') {
  return `<div class="tools"><label class="field">${ic('search')}<input id="q" placeholder="Search" value="${esc(S.q)}"></label>${extra}
  <div class="seg"><button data-mode="grid" class="${S.mode === 'grid' ? 'on' : ''}" title="Cards">${ic('grid')}</button><button data-mode="list" class="${S.mode === 'list' ? 'on' : ''}" title="List">${ic('list')}</button></div></div>`;
}
function filtered(base) {
  const q = S.q.toLowerCase();
  return base.filter(j => (!q || (j.title + ' ' + j.company + ' ' + j.source).toLowerCase().includes(q)) && (!S.fStatus || j.status === S.fStatus) && (!S.fHow || j.method === S.fHow) &&
    (j.score || 0) >= S.fScore && (!S.onlyPicked || j.picked) && (!S.source || j.source === S.source));
}
function filters() {
  const opt = (v, l, cur) => `<option value="${v}" ${String(cur) === String(v) ? 'selected' : ''}>${l}</option>`;
  return `<label class="field">${ic('filter')}<select id="fScore">${[[0, 'Any score'], [3, 'Score 3+'], [4, 'Score 4+'], [5, 'Score 5']].map(([v, l]) => opt(v, l, S.fScore)).join('')}</select></label>
  <label class="field"><select id="fHow">${opt('', 'Any way to apply', S.fHow)}${Object.entries(HOW).map(([k, [, t]]) => opt(k, t, S.fHow)).join('')}</select></label>
  <label class="field"><select id="fStatus">${opt('', 'Any status', S.fStatus)}${S.stats.statuses.filter(s => S.stats.by_status[s]).map(s => opt(s, s + ' (' + S.stats.by_status[s] + ')', S.fStatus)).join('')}</select></label>
  <label class="field" style="cursor:pointer"><input type="checkbox" id="onlyPicked" ${S.onlyPicked ? 'checked' : ''} style="width:auto"> Picked only</label>`;
}
function header(title, tabs) {
  const np = picked().length;
  return `<div class="crumb">${esc(S.view === 'home' ? 'JobSidekick' : 'Home')}</div>
  <div class="head"><h1>${esc(title)}</h1><div class="btns">
    <button class="btn primary" data-act="findbox">${ic('search')} Find Jobs</button>
    <button class="btn" data-act="linkbox">${ic('link')} Add by Link</button>
    <button class="btn" data-act="applybox">${ic('bolt')} Apply${np ? ' (' + np + ' picked)' : ''}</button></div></div>
  ${tabs ? `<div class="tabs">${tabs.map(([k, l, i]) => `<button class="tab ${S.tab === k ? 'on' : ''}" data-tab="${k}">${ic(i)} ${l}</button>`).join('')}</div>` : ''}`;
}

/* ---------- timeline ---------- */
function timeline() {
  const a = S.act; if (!a) return '';
  const n = a.n, start = new Date(a.start * 1000), W = 100 / n;
  const fmt = { day: d => d.toLocaleTimeString([], { hour: 'numeric' }), week: d => d.toLocaleDateString([], { weekday: 'short' }), month: d => d.getDate(), year: d => d.toLocaleDateString([], { month: 'short' }) }[S.span];
  const label = i => fmt(new Date((a.start + i * a.step) * 1000));
  const every = n > 14 ? 5 : 1;
  const axis = Array.from({ length: n }, (_, i) => i % every === 0 ? `<span style="left:${(i + .5) * W}%">${label(i)}</span>` : '').join('');
  const rows = Object.entries(a.rows).map(([name, b]) => {
    const bars = b.map((c, i) => c ? `<div class="bar ${name}" style="left:calc(${i * W}% + 2px);width:calc(${W}% - 4px);justify-content:center;padding:0" title="${c} ${name.toLowerCase()}">${c}</div>` : '').join('');
    return `<div class="tlname">${name}</div><div class="tlrow" style="--w:${W}%">${bars}</div>`;
  }).join('');
  const total = Object.values(a.rows).flat().reduce((x, y) => x + y, 0);
  return `<div class="tl"><div class="tlh"><b>Activity · ${start.toLocaleDateString([], { month: 'short', day: 'numeric' })} to today</b>
    <div class="range">${['day', 'week', 'month', 'year'].map(s => `<button data-span="${s}" class="${S.span === s ? 'on' : ''}">${s[0].toUpperCase() + s.slice(1)}</button>`).join('')}</div></div>
    ${total ? `<div class="tlgrid">${rows}<div></div><div class="tlrow axis">${axis}</div></div>` : '<div class="empty" style="border:0">No activity in this period yet.</div>'}</div>`;
}

/* ---------- views ---------- */
function vHome() {
  const st = S.stats, c = st.by_status || {};
  const tabs = [['overview', 'Overview', 'home'], ['pipeline', 'Pipeline', 'board'], ['all', 'All jobs', 'jobs']];
  let body;
  if (S.tab === 'pipeline') body = pipeline();
  else if (S.tab === 'all') { const js = filtered(S.jobs); body = `<div class="sec"><h2>All jobs <small style="color:var(--dim);font-weight:400">${js.length}</small></h2>${toolbar(filters())}</div>${listOf(js, S.shown)}${more(js.length, S.shown)}`; }
  else {
    const rank = { ready: 0, drafted: 1, matched: 2, applied: 3 }, top = S.jobs.filter(j => ['ready', 'drafted', 'matched'].includes(j.status)).sort((a, b) => (rank[a.status] - rank[b.status]) || (b.score - a.score));
    const js = filtered(top.length ? top : S.jobs.filter(j => j.score)).slice(0, 8);
    body = `<div class="stats">${[['Found', st.found], ['Scored', st.scored], ['Ready to apply', c.ready || 0], ['Applied / drafted', st.applied_or_drafted], ['Interviews', st.interviews]].map(([l, v]) => `<div class="stat"><b>${v ?? 0}</b><small>${l}</small></div>`).join('')}</div>
    <div class="sec"><h2>Top matches</h2>${toolbar(filters())}</div>${listOf(js, 8)}
    ${S.jobs.length > 8 ? `<p style="margin-top:14px"><a class="btn small" data-go="queue" style="text-decoration:none">View all ready jobs ${ic('arrow')}</a></p>` : ''}${timeline()}`;
  }
  return header('Home', tabs) + body;
}
function vJobs() { const js = filtered(S.jobs); return header(S.source ? 'Source: ' + S.source : 'All jobs') + `<div class="sec"><h2>${js.length} jobs</h2>${toolbar(filters())}</div>${listOf(js, S.shown)}${more(js.length, S.shown)}`; }
function vQueue() {
  const js = filtered(S.jobs.filter(j => ['ready', 'drafted'].includes(j.status)));
  return header('Ready to apply') + `<div class="sec"><h2>${js.length} ready <small style="color:var(--dim);font-weight:400">· pick the ones you want, then use Apply</small></h2>${toolbar(filters())}</div>${listOf(js, S.shown)}${more(js.length, S.shown)}`;
}
function pipeline() {
  const cols = [['ready', 'Ready'], ['drafted', 'Drafted'], ['applied', 'Applied'], ['interview', 'Interview'], ['offer', 'Offer'], ['rejected', 'Rejected']];
  return `<div class="sec"><h2>Pipeline</h2><small style="color:var(--dim)">Change a job's status in its panel as things happen.</small></div><div class="board">${cols.map(([k, l]) => {
    const js = S.jobs.filter(j => j.status === k);
    return `<div class="col"><h4>${l}<span>${js.length}</span></h4>${js.slice(0, 40).map(j => `<div class="mini" data-open="${esc(j.id)}"><b>${esc(j.title)}</b><small>${esc(j.company)} · ${j.score || '–'}/5</small></div>`).join('') || '<small style="color:var(--dim);padding:6px">Nothing</small>'}</div>`;
  }).join('')}</div>`;
}
function vPipeline() { return header('Pipeline') + pipeline(); }
function vManual() {
  const js = S.jobs.filter(j => j.method === 'login' || j.status === 'manual').filter(j => !['applied', 'skipped', 'closed'].includes(j.status));
  return header('Apply by hand') + `<div class="sec"><h2>${js.length} to do yourself</h2><small style="color:var(--dim)">Sites that need a login, plus anything the tool couldn't finish.</small></div>` +
    (js.length ? `<div class="grid">${js.map(card).join('')}</div>` : `<div class="empty"><b>Nothing waiting</b>Jobs that need a login or a CAPTCHA will show up here, with your cover letter ready to copy.</div>`);
}
function vInsights() {
  const st = S.stats, max = Math.max(1, ...st.by_source.map(r => r[1]));
  const f = [['Found', st.found], ['Scored', st.scored], ['Matched', st.matched], ['Applied or drafted', st.applied_or_drafted], ['Interviews', st.interviews], ['Offers', st.offers]];
  return header('Insights') + `<div class="sec"><h2>Funnel</h2></div><div class="bars">${f.map(([l, v]) => `<div class="brow"><span>${l}</span><i style="width:${Math.max(2, v / Math.max(1, st.found) * 100)}%"></i><b>${v}</b></div>`).join('')}</div>
  <div class="sec"><h2>Where jobs come from</h2></div><div class="bars">${st.by_source.map(([s, n, w]) => `<div class="brow"><a data-source="${esc(s)}" style="cursor:pointer;text-decoration:underline dotted">${esc(s)}</a><i style="width:${n / max * 100}%"></i><b>${n}</b></div>`).join('')}</div>
  <div class="sec"><h2>Skills jobs ask for that your CV lacks</h2></div>${st.gaps.length ? `<div class="chips">${st.gaps.map(([g, n]) => `<span class="chip">${esc(g)} · ${n}</span>`).join('')}</div>` : '<div class="empty">Gaps appear after jobs are scored.</div>'}
  ${timeline()}`;
}
async function vAnswers() {
  S.answers = await get('/api/answers');
  return header('Saved answers') + `<div class="sec"><h2>Answers reused on every form</h2></div>
  <div class="kv" style="grid-template-columns:1fr"><input class="in" id="aq" placeholder="Question, e.g. Why do you want to work here?"><textarea id="aa" rows="3" placeholder="Your answer"></textarea><div><button class="btn primary" data-act="saveanswer">Save answer</button></div></div>
  <div style="margin-top:18px">${S.answers.map(a => `<div class="qa"><b>${esc(a.question)}</b><span>${esc(a.answer)}</span></div>`).join('') || '<div class="empty">No saved answers yet. They are also saved when you answer a question while applying.</div>'}</div>`;
}
function vSettings() {
  const s = S.settings;
  return header('Settings') + `<div class="sec"><h2>Current setup</h2><small style="color:var(--dim)">Edit config.yaml to change these.</small></div><dl class="kv">
  <dt>AI provider</dt><dd>${esc(s.provider)} · ${esc(Object.values(s.models || {}).join(', '))}</dd><dt>Apply mode</dt><dd>${esc(s.mode)} <small style="color:var(--dim)">(review = you confirm each submit)</small></dd>
  <dt>Minimum score</dt><dd>${esc(s.min_score)}</dd><dt>Searching for</dt><dd>${(s.titles || []).map(t => `<span class="chip">${esc(t)}</span>`).join(' ')}</dd>
  <dt>Resumes</dt><dd>${s.resume ? 'Tailored per job' : 'Off'}</dd><dt>Emails</dt><dd>${esc(s.email_via)}</dd><dt>Sources on</dt><dd>${(s.sources_on || []).map(t => `<span class="chip">${esc(t)}</span>`).join(' ')}</dd></dl>`;
}
function vCommands() {
  const C = [['Find, score, draft', 'uv run sidekick run'], ['Apply to web forms (you confirm each Submit)', 'uv run sidekick apply --limit 1'], ['Apply by email (Gmail drafts)', 'uv run sidekick email'], ['Sign in once to a site', 'uv run sidekick login https://…'], ['Preview a Greenhouse form', 'uv run sidekick plan'], ['Work through login-only jobs', 'uv run sidekick manual'], ['Interview prep for a job', 'uv run sidekick prep <job id>'], ['Outreach drafts', 'uv run sidekick outreach'], ['Schedule the daily routine', 'uv run sidekick schedule install --time 09:00']];
  return header('Commands') + `<div class="sec"><h2>Things that run in a terminal</h2><small style="color:var(--dim)">Run from the project folder.</small></div>${C.map(([l, c]) => `<p style="margin:12px 0 4px">${l}</p><div class="cmd"><code>${esc(c)}</code><button data-copy="${esc(c)}">${ic('copy')}</button></div>`).join('')}`;
}
const VIEWS = { home: vHome, jobs: vJobs, queue: vQueue, pipeline: vPipeline, manual: vManual, insights: vInsights, answers: vAnswers, settings: vSettings, commands: vCommands, source: vJobs };

/* ---------- shell ---------- */
function sidebar() {
  const c = S.stats.by_status || {}, cnt = { jobs: S.stats.found, queue: (c.ready || 0) + (c.drafted || 0), manual: S.jobs.filter(j => j.method === 'login' && !['applied', 'skipped', 'closed'].includes(j.status)).length };
  const p = S.profile || {};
  return `<aside class="side">
  <div class="ws"><div class="logo">${esc((p.name || 'J')[0])}</div><div class="grow"><b>${esc(p.name || 'JobSidekick')}</b><small>${esc(p.title || 'Your job-search sidekick')}</small></div></div>
  <button class="searchbtn" data-act="palette">${ic('search')}<span>Search or run…</span><span class="kbd">⌘K</span></button>
  <nav class="nav"><h6>Essentials</h6>${NAV.map(([k, l, i]) => `<a class="item ${S.view === k ? 'on' : ''}" data-go="${k}">${ic(i)} ${l}${cnt[k] ? `<span class="count">${cnt[k]}</span>` : ''}</a>`).join('')}
  <details class="group" open><summary>${ic('jobs')} Sources<span class="plus">${ic('plus')}</span></summary>${(S.stats.by_source || []).slice(0, 8).map(([s, n]) => `<a class="item ${S.view === 'source' && S.source === s ? 'on' : ''}" data-source="${esc(s)}"><span class="dot" style="background:${PAL[hash(s) % PAL.length][0]};border:1px solid ${PAL[hash(s) % PAL.length][1]}55"></span>${esc(s)}<span class="count">${n}</span></a>`).join('')}</details>
  <details class="group" open><summary>${ic('cog')} Support</summary><a class="item ${S.view === 'settings' ? 'on' : ''}" data-go="settings">${ic('cog')} Settings</a><a class="item ${S.view === 'commands' ? 'on' : ''}" data-go="commands">${ic('term')} Commands</a></details></nav></aside>`;
}
async function draw() {
  const v = S.view; let html = VIEWS[v](); if (html instanceof Promise) html = await html;
  const keepQ = document.activeElement && document.activeElement.id === 'q' ? document.activeElement.selectionStart : null;
  $('#app').innerHTML = `<div class="shell">${sidebar()}<main class="main"><div class="inner">${html}</div></main></div>`;
  if (keepQ !== null) { const q = $('#q'); if (q) { q.focus(); q.setSelectionRange(keepQ, keepQ); } }
  drawRun();
}
function go(view, extra = {}) { Object.assign(S, { view, shown: 60, q: '', fStatus: '', fHow: '', fScore: 0, onlyPicked: false, source: '' }, extra); if (view === 'home') S.tab = 'overview'; draw(); $('.main')?.scrollTo(0, 0); }

/* ---------- drawer ---------- */
async function openJob(id) {
  const j = await get('/api/job/' + encodeURIComponent(id)); if (!j.id) return;
  let gaps = []; try { gaps = JSON.parse(j.gaps || '[]'); } catch { }
  const sts = S.stats.statuses.map(s => `<option ${s === j.status ? 'selected' : ''}>${s}</option>`).join('');
  $('#drawer').innerHTML = `<div class="scrim" data-close></div><aside class="drawer"><button class="xbtn" data-close>${ic('x')}</button>${avatar(j.company || j.title)}
  <h2>${esc(j.title)}</h2><div class="sub">${esc(j.company)} · ${esc((j.location || '').slice(0, 60))} ${j.salary ? '· ' + esc(j.salary) : ''}</div>
  <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">${howPill(j)}${stPill(j.status)}<span class="pill gray">${esc(j.source)}</span>${j.email ? `<span class="pill blue">${esc(j.email)}</span>` : ''}</div>
  <div class="blk"><h5>Fit score</h5>${scoreBar(j.score)}<p style="margin:8px 0 0;color:var(--ink2)">${esc(j.reasons || 'Not scored yet. Use “Score new jobs” from ⌘K.')}</p></div>
  ${gaps.length ? `<div class="blk"><h5>Skills they want that your CV lacks</h5><div class="chips">${gaps.map(g => `<span class="chip">${esc(g)}</span>`).join('')}</div></div>` : ''}
  ${j.notes ? `<div class="blk"><h5>Notes</h5>${esc(j.notes)}</div>` : ''}
  <div class="blk"><h5>Actions</h5><div class="btns"><a class="btn small" href="${esc(j.url)}" target="_blank" rel="noopener" style="text-decoration:none">${ic('ext')} Open posting</a>
    ${j.resume_path ? `<a class="btn small" href="/resume/${encodeURIComponent(j.id)}" target="_blank" style="text-decoration:none">${ic('file')} Tailored resume</a>` : ''}
    <button class="btn small" data-pick="${esc(j.id)}" data-keep>${ic('check')} ${j.picked ? 'Unpick' : 'Pick to apply'}</button>
    ${j.cover_letter ? `<button class="btn small" data-copy="${esc(j.cover_letter)}">${ic('copy')} Copy cover letter</button>` : ''}</div></div>
  <div class="blk"><h5>Status</h5><select class="in" data-status="${esc(j.id)}">${sts}</select></div>
  ${j.cover_letter ? `<div class="blk"><h5>Cover letter</h5><pre>${esc(j.cover_letter)}</pre></div>` : ''}
  <div class="blk"><h5>Posting</h5><pre>${esc((j.description || '').slice(0, 3500))}</pre></div></aside>`;
}
const closeDrawer = () => { $('#drawer').innerHTML = ''; };

/* ---------- palette (⌘K) ---------- */
function palItems(q) {
  const t = q.trim(), isUrl = /^https?:\/\//i.test(t), out = [];
  const A = (g, ic_, title, sub, run) => out.push({ g, ic: ic_, title, sub, run });
  if (isUrl) A('Do', 'link', 'Add this job from its link', t.slice(0, 70), () => run('add', { url: t }));
  else if (t) A('Do', 'search', `Find jobs for “${t}”`, 'Searches every source, then scores what is new', () => run('find', { query: t }));
  if (t && !isUrl) A('Do', 'jobs', `Search my jobs for “${t}”`, 'Filters the list you already have', () => { go('jobs', { q: t }); });
  const acts = [['bolt', 'Find jobs now', 'Scan all sources and score new jobs', () => run('find')], ['chart', 'Score new jobs', 'AI rates each one against your CV', () => run('score')], ['file', 'Write cover letters', 'For jobs that matched', () => run('draft')],
    ['mail', 'Prepare picked jobs', 'Tailored resume and email drafts for jobs you picked', () => run('prepare')], ['sync', 'Sync Gmail', 'Update statuses from replies; import LinkedIn alerts', () => run('sync')], ['cal', 'Run the daily routine', 'Find, score, draft, sync, digest', () => run('daily')],
    ['bolt', 'Apply to picked jobs…', 'Shows the terminal command (you confirm each submit)', () => modal('apply')]];
  acts.filter(a => !t || (a[1] + ' ' + a[2]).toLowerCase().includes(t.toLowerCase())).forEach(a => A('Actions', ...a));
  NAV.concat([['settings', 'Settings', 'cog'], ['commands', 'Commands', 'term']]).filter(n => !t || n[1].toLowerCase().includes(t.toLowerCase())).forEach(n => A('Go to', n[2], n[1], '', () => go(n[0])));
  if (t && !isUrl) S.jobs.filter(j => (j.title + ' ' + j.company).toLowerCase().includes(t.toLowerCase())).slice(0, 5).forEach(j => A('Jobs', 'jobs', j.title, `${j.company} · ${j.score || '–'}/5 · ${j.status}`, () => openJob(j.id)));
  return out;
}
function openPalette(prefill = '') { S.pal = { q: prefill, i: 0 }; $('#palette').innerHTML = `<div class="scrim" data-pclose></div><div class="pal"><input id="pq" placeholder="Type a job to find, paste a link, or search an action…" autocomplete="off" value="${esc(prefill)}"><div class="list" id="plist"></div><div class="foot"><span>↑↓ move</span><span>↵ run</span><span>esc close</span></div></div>`; palDraw(); $('#pq').focus(); }
function palDraw() {
  const items = S.pal.items = palItems($('#pq').value); S.pal.i = Math.min(S.pal.i, Math.max(0, items.length - 1)); let g = '';
  $('#plist').innerHTML = items.map((it, i) => (it.g !== g ? (g = it.g, `<h6>${it.g}</h6>`) : '') + `<div class="opt ${i === S.pal.i ? 'on' : ''}" data-pi="${i}"><span class="ic">${ic(it.ic)}</span><div><b>${esc(it.title)}</b>${it.sub ? `<small>${esc(it.sub)}</small>` : ''}</div></div>`).join('') || '<div class="empty" style="border:0">No matches</div>';
}
const closePalette = () => { $('#palette').innerHTML = ''; S.pal = null; };
function palRun(i) { const it = S.pal.items[i]; closePalette(); if (it) it.run(); }

/* ---------- modal ---------- */
function modal(kind) {
  const np = picked().length;
  const m = {
    apply: `<h3>Apply to ${np ? np + ' picked job' + (np > 1 ? 's' : '') : 'your ready jobs'}</h3><p>Applying opens a real browser and fills each form. <b>You press Submit</b> in the terminal prompt, so nothing is sent without you. Run these in a terminal, from the project folder:</p>
      ${np ? '' : '<p style="color:var(--orange)">No jobs picked yet. Tick the boxes on the jobs you want, otherwise it uses every ready job.</p>'}
      ${[['1. Tailored resume + cover letter', 'uv run sidekick resume'], ['2. Jobs that apply by email (Gmail drafts)', 'uv run sidekick email'], ['3. Web forms, one at a time', 'uv run sidekick apply --limit 1'], ['4. Login-only sites', 'uv run sidekick manual']].map(([l, c]) => `<p style="margin:10px 0 4px">${l}</p><div class="cmd"><code>${c}</code><button data-copy="${c}">${ic('copy')}</button></div>`).join('')}
      <div class="btns" style="margin-top:14px"><button class="btn primary" data-act="prep">Prepare picked jobs now</button><button class="btn" data-mclose>Close</button></div>`,
    find: `<h3>Find jobs</h3><p>Search every source for a role, then score what is new against your CV.</p><input class="in" id="fq" placeholder="e.g. react developer, node.js (blank = your saved searches)"><div class="btns" style="margin-top:14px"><button class="btn primary" data-act="dofind">${ic('search')} Find</button><button class="btn" data-mclose>Cancel</button></div>`,
    link: `<h3>Add a job by link</h3><p>Paste a posting link. It is read, scored and queued like any other job.</p><input class="in" id="lq" placeholder="https://…"><div class="btns" style="margin-top:14px"><button class="btn primary" data-act="doadd">${ic('link')} Add</button><button class="btn" data-mclose>Cancel</button></div>`,
  }[kind];
  $('#modal').innerHTML = `<div class="scrim" data-mclose></div><div class="modal">${m}</div>`; $('#fq,#lq')?.focus();
}
const closeModal = () => { $('#modal').innerHTML = ''; };

/* ---------- runs ---------- */
async function run(action, body = {}) {
  const r = await post('/api/run', { action, ...body });
  if (r.error) { toast(r.error); return; }
  S.run = r; drawRun(); pollRun();
}
let timer;
function pollRun() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const r = await get('/api/run'); if (r && r.id) S.run = r; drawRun();
    if (S.run && S.run.status === 'running') pollRun(); else { await load('quiet'); }
  }, 1500);
}
function drawRun() {
  const r = S.run, el = $('#runpanel'); if (!r || r.dismissed) { el.innerHTML = ''; return; }
  const cls = r.status === 'done' ? 'done' : r.status === 'failed' ? 'failed' : '';
  el.innerHTML = `<div class="run"><header><b>${esc(r.label)}</b><span><span class="pill ${r.status === 'done' ? 'green' : r.status === 'failed' ? 'red' : 'blue'}">${r.status === 'running' ? `step ${r.step}/${r.steps}` : r.status}</span> <button class="xbtn" style="width:26px;height:26px;float:none" data-runx>${ic('x')}</button></span></header>
  <div class="prog ${cls}"><i></i></div><pre id="runlog">${esc((r.log || []).slice(-8).join('\n'))}</pre></div>`;
  const l = $('#runlog'); if (l) l.scrollTop = l.scrollHeight;
}
function toast(msg) { S.run = { id: 'x', label: msg, status: 'failed', log: [], step: 1, steps: 1 }; drawRun(); }

/* ---------- events ---------- */
document.addEventListener('click', async e => {
  const t = e.target;
  const pb = t.closest('[data-pick]'); if (pb) { e.stopPropagation(); const j = byId(pb.dataset.pick), v = !(j && j.picked); await post(`/api/job/${encodeURIComponent(pb.dataset.pick)}/pick`, { picked: v }); if (j) j.picked = v ? 1 : 0; draw(); if (pb.hasAttribute('data-keep')) openJob(pb.dataset.pick); return; }
  if (t.closest('[data-copy]')) { navigator.clipboard?.writeText(t.closest('[data-copy]').dataset.copy); t.closest('[data-copy]').innerHTML = ic('check'); return; }
  const act = t.closest('[data-act]')?.dataset.act;
  if (act === 'palette') return openPalette();
  if (act === 'findbox') return modal('find');
  if (act === 'linkbox') return modal('link');
  if (act === 'applybox') return modal('apply');
  if (act === 'dofind') { const q = $('#fq').value.trim(); closeModal(); return run('find', q ? { query: q } : {}); }
  if (act === 'doadd') { const u = $('#lq').value.trim(); closeModal(); return run('add', { url: u }); }
  if (act === 'prep') { closeModal(); return run('prepare'); }
  if (act === 'saveanswer') { const q = $('#aq').value.trim(), a = $('#aa').value.trim(); if (q && a) { await post('/api/answers', { question: q, answer: a }); draw(); } return; }
  if (t.closest('[data-close]')) return closeDrawer();
  if (t.closest('[data-pclose]')) return closePalette();
  if (t.closest('[data-mclose]')) return closeModal();
  if (t.closest('[data-runx]')) { S.run.dismissed = true; return drawRun(); }
  const pi = t.closest('[data-pi]'); if (pi) return palRun(+pi.dataset.pi);
  const g = t.closest('[data-go]'); if (g) return go(g.dataset.go);
  const sr = t.closest('[data-source]'); if (sr) return go('source', { source: sr.dataset.source });
  const tab = t.closest('[data-tab]'); if (tab) { S.tab = tab.dataset.tab; return draw(); }
  const m = t.closest('[data-mode]'); if (m) { S.mode = m.dataset.mode; return draw(); }
  const sp = t.closest('[data-span]'); if (sp) { S.span = sp.dataset.span; S.act = await get('/api/activity?span=' + S.span); return draw(); }
  if (t.closest('[data-more]')) { S.shown += 60; return draw(); }
  const o = t.closest('[data-open]'); if (o) return openJob(o.dataset.open);
});
document.addEventListener('input', e => {
  const t = e.target;
  if (t.id === 'pq') { S.pal.i = 0; return palDraw(); }
  if (t.id === 'q') { S.q = t.value; S.shown = 60; return draw(); }
  if (t.id === 'fScore') { S.fScore = +t.value; return draw(); }
  if (t.id === 'fHow') { S.fHow = t.value; return draw(); }
  if (t.id === 'fStatus') { S.fStatus = t.value; return draw(); }
  if (t.id === 'onlyPicked') { S.onlyPicked = t.checked; return draw(); }
  if (t.dataset.status) { post(`/api/job/${encodeURIComponent(t.dataset.status)}/status`, { status: t.value }).then(() => load('quiet')); }
});
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); return S.pal ? closePalette() : openPalette(); }
  if (e.key === 'Escape') { if (S.pal) closePalette(); else if ($('#modal').innerHTML) closeModal(); else closeDrawer(); }
  if (S.pal && ['ArrowDown', 'ArrowUp', 'Enter'].includes(e.key)) {
    e.preventDefault(); const n = S.pal.items.length;
    if (e.key === 'Enter') return palRun(S.pal.i);
    S.pal.i = (S.pal.i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n; palDraw(); $('.opt.on')?.scrollIntoView({ block: 'nearest' });
  }
  if (e.key === 'Enter' && e.target.id === 'fq') $('[data-act=dofind]').click();
  if (e.key === 'Enter' && e.target.id === 'lq') $('[data-act=doadd]').click();
});

load().then(async () => { const r = await get('/api/run'); if (r && r.id && r.status === 'running') { S.run = r; pollRun(); drawRun(); } });
})();

/* PR-Sing 前端（原生 JS，无依赖） */
"use strict";

let TOKEN = localStorage.getItem("prsing_token") || "";

async function api(path, method, body) {
  const opt = { method: method || "GET", headers: {} };
  if (body !== undefined) {
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  if (TOKEN) opt.headers["Authorization"] = "Bearer " + TOKEN;
  let r;
  try {
    r = await fetch(path, opt);
  } catch (e) {
    return { ok: false, error: "网络错误: " + e };
  }
  let j;
  try { j = await r.json(); } catch (e) { j = { ok: false, error: "响应解析失败" }; }
  if (r.status === 401 && !path.startsWith("/api/login")) showLogin();
  return j;
}

function $(id) { return document.getElementById(id); }
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function esc(s) { return String(s == null ? "" : s); }
function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString() : "-"; }
function msg(id, text, kind) {
  const m = $(id);
  if (!m) return;
  m.textContent = text || "";
  m.className = "msg" + (kind ? " " + kind : "");
}
function cell(node, html) {
  const td = el("td");
  if (node) td.appendChild(node);
  else td.innerHTML = html || "";
  return td;
}

/* ---------------- 登录 ---------------- */
function showLogin() {
  $("app").classList.add("hidden");
  $("login-view").classList.remove("hidden");
  setTimeout(() => $("login-pw").focus(), 50);
}
function showApp() {
  $("login-view").classList.add("hidden");
  $("app").classList.remove("hidden");
  switchTab("status");
}
async function doLogin() {
  const r = await api("/api/login", "POST", { password: $("login-pw").value });
  if (r.ok) {
    TOKEN = r.token;
    localStorage.setItem("prsing_token", TOKEN);
    showApp();
  } else msg("login-err", r.error || "登录失败");
}

/* ---------------- 标签页 ---------------- */
function switchTab(t) {
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach(s => s.classList.toggle("on", s.id === "tab-" + t));
  if (t === "status") refreshStatus();
  else if (t === "nodes") refreshNodes();
  else if (t === "subs") refreshSubs();
  else if (t === "chains") refreshChains();
  else if (t === "groups") refreshGroups();
  else if (t === "rules") refreshRules();
  else if (t === "settings") refreshSettings();
}

function renderKv(id, rows) {
  const box = $(id);
  if (!box) return;
  box.innerHTML = "";
  for (const [k, v] of rows) {
    const line = el("div");
    line.style.display = "flex";
    line.style.gap = "10px";
    line.style.padding = "3px 0";
    const a = el("span", null, k);
    a.style.color = "var(--dim)";
    a.style.minWidth = "120px";
    a.style.flexShrink = "0";
    const b = el("span", null, String(v == null ? "-" : v));
    b.style.wordBreak = "break-all";
    line.appendChild(a); line.appendChild(b);
    box.appendChild(line);
  }
}

/* ---------------- 状态 ---------------- */
async function refreshStatus() {
  const r = await api("/api/status");
  if (!r.ok) return;
  const c = r.core || {};
  const badge = $("core-badge");
  badge.textContent = c.running ? "内核: 运行中 (PID " + c.pid + ")" : "内核: 已停止";
  badge.className = "badge " + (c.running ? "on" : "off");
  renderKv("core-info", [
    ["版本", c.version],
    ["二进制", c.core_bin_ok ? c.core_bin : "缺失: " + c.core_bin],
    ["TUN", c.tun_enabled ? c.tun_interface + (c.tun_present ? "（在线）" : "（未检测到）") : "关闭"],
    ["Mixed", c.mixed_enabled ? c.mixed_port : "关闭"],
    ["配置文件", c.config],
    ["日志文件", c.log],
  ]);
  const cnt = r.counts || {};
  renderKv("stat-info", [
    ["节点数", cnt.nodes],
    ["链数", cnt.chains],
    ["组数", cnt.groups],
    ["订阅数", cnt.subs],
    ["面板版本", r.version],
    ["分流模式", c.route_mode],
    ["DNS 模式", c.dns_mode],
  ]);
  const rs = (r.rules || {}).rule_sets || {};
  const rows = Object.keys(rs).map(k => [k, rs[k].exists ? rs[k].size + " B" : "缺失"]);
  const geo = (r.rules || {}).geo || {};
  for (const k in geo) rows.push(["geo:" + k, geo[k].exists ? geo[k].size + " B" : "缺失"]);
  renderKv("rules-info", rows);
}
async function refreshLogs() {
  const r = await api("/api/logs?n=300");
  if (r.ok) $("log-view").textContent = (r.lines || []).join("\n") || "(空)";
}
async function coreAction(action) {
  const m = $("core-msg");
  m.textContent = action + " 中…"; m.className = "msg";
  const r = await api("/api/core/" + action, "POST", {});
  if (r.ok) {
    m.textContent = "OK: " + (r.detail || "") + (r.output ? "\n" + r.output.slice(-800) : "");
    m.className = "msg ok";
  } else {
    m.textContent = (r.error || r.detail || "失败") + (r.output ? "\n" + r.output.slice(-1200) : "");
    m.className = "msg err";
  }
  refreshStatus();
}
async function coreRegen() {
  const m = $("core-msg");
  m.textContent = "校验中…"; m.className = "msg";
  const r = await api("/api/core/regen", "POST", {});
  if (r.ok && r.check) {
    m.textContent = r.check.ok ? "配置校验通过 ✓" : "校验失败:\n" + r.check.output.slice(-1200);
    m.className = "msg " + (r.check.ok ? "ok" : "err");
  } else { m.textContent = r.error || "失败"; m.className = "msg err"; }
}

/* ---------------- 节点 ---------------- */
async function refreshNodes() {
  const r = await api("/api/nodes");
  if (!r.ok) return;
  const tb = $("node-table").querySelector("tbody");
  tb.innerHTML = "";
  for (const n of (r.nodes || [])) {
    const tr = el("tr");
    const addr = n.cfg && n.cfg.server ? (n.cfg.server + ":" + (n.cfg.server_port || "")) : "-";
    tr.appendChild(cell(null, esc(n.name)));
    tr.appendChild(cell(null, "<span class='pill'>" + esc(n.type) + "</span>"));
    tr.appendChild(cell(null, esc(addr)));
    const latHtml = n.latency == null ? "-" :
      "<span style='color:" + (n.latency < 500 ? "var(--ok)" : "var(--warn)") + "'>" + n.latency + "ms</span>";
    tr.appendChild(cell(null, latHtml));
    const cb = el("input");
    cb.type = "checkbox"; cb.checked = !!n.enabled;
    cb.onchange = async () => {
      const u = await api("/api/nodes/" + n.id, "PUT", { enabled: cb.checked });
      if (!u.ok) msg("node-parse-msg", u.error, "err");
      refreshNodes();
    };
    tr.appendChild(cell(cb));
    const ops = el("td");
    const bLat = el("button", "sm ghost", "测速");
    bLat.onclick = async () => {
      bLat.textContent = "…";
      const t = await api("/api/nodes/" + n.id + "/latency", "POST", {});
      bLat.textContent = "测速";
      if (t.ok) msg("node-parse-msg", n.name + " 延迟 " + t.ms + "ms", "ok");
      else msg("node-parse-msg", n.name + ": " + (t.error || "失败"), "err");
      refreshNodes();
    };
    const bEdit = el("button", "sm ghost", "编辑");
    bEdit.onclick = () => editNodeModal(n);
    const bDel = el("button", "sm danger", "删除");
    bDel.onclick = async () => {
      if (!confirm("删除节点 " + n.name + "？")) return;
      await api("/api/nodes/" + n.id, "DELETE");
      refreshNodes(); refreshChains(); refreshGroups();
    };
    ops.appendChild(bLat); ops.appendChild(bEdit); ops.appendChild(bDel);
    tr.appendChild(ops);
    tb.appendChild(tr);
  }
}
function editNodeModal(n) {
  const body = $("modal-body");
  body.innerHTML = "";
  body.appendChild(el("h2", null, "编辑节点: " + esc(n.name)));
  const nameIn = el("input");
  nameIn.value = n.name; nameIn.placeholder = "名称";
  const enCk = el("input");
  enCk.type = "checkbox"; enCk.checked = !!n.enabled;
  const ta = el("textarea");
  ta.rows = 12; ta.value = JSON.stringify(n.cfg, null, 2);
  ta.style.fontFamily = "ui-monospace, Consolas, monospace";
  ta.style.fontSize = "12px";
  ta.style.width = "100%";
  body.appendChild(el("div", "row", nameIn));
  const ckRow = el("div", "row");
  ckRow.appendChild(enCk);
  ckRow.appendChild(el("label", "hint", "启用"));
  body.appendChild(ckRow);
  body.appendChild(el("div", "hint", "sing-box outbound 配置（JSON）"));
  body.appendChild(ta);
  const row = el("div", "row");
  const bSave = el("button", null, "保存");
  const bClose = el("button", "ghost", "关闭");
  bSave.onclick = async () => {
    let cfg;
    try { cfg = JSON.parse(ta.value); } catch (e) { alert("JSON 无效: " + e); return; }
    const u = await api("/api/nodes/" + n.id, "PUT", { name: nameIn.value, enabled: enCk.checked, cfg: cfg });
    if (u.ok) { closeModal(); refreshNodes(); refreshChains(); refreshGroups(); }
    else msg("node-parse-msg", u.error, "err");
  };
  bClose.onclick = closeModal;
  row.appendChild(bSave); row.appendChild(bClose);
  body.appendChild(row);
  $("modal").classList.remove("hidden");
}
function closeModal() { $("modal").classList.add("hidden"); }

async function parseLinks() {
  const r = await api("/api/nodes/parse", "POST", { text: $("node-import-text").value });
  const box = $("node-parse-list");
  box.innerHTML = "";
  if (r.ok) {
    const items = r.parsed || [];
    msg("node-parse-msg", "解析出 " + items.length + " 条节点" + (r.errors.length ? "，" + r.errors.length + " 条失败" : ""), "ok");
    for (const p of items) {
      const d = el("span", "pill", p.name + " [" + p.type + "] " + (p.cfg.server || "") + ":" + (p.cfg.server_port || ""));
      box.appendChild(d);
      box.appendChild(el("span", null, " "));
    }
    for (const e of (r.errors || [])) box.appendChild(el("div", "hint", "✗ " + e));
  } else msg("node-parse-msg", r.error, "err");
}
async function importLinks() {
  const r = await api("/api/nodes/import", "POST", { text: $("node-import-text").value });
  if (r.ok) {
    msg("node-parse-msg", "已添加 " + r.added + " 个节点" + (r.errors.length ? "（" + r.errors.length + " 条失败）" : ""), "ok");
    refreshNodes(); refreshChains(); refreshGroups();
  } else msg("node-parse-msg", r.error, "err");
}

/* ---------------- 订阅 ---------------- */
async function refreshSubs() {
  const r = await api("/api/subs");
  if (!r.ok) return;
  const tb = $("sub-table").querySelector("tbody");
  tb.innerHTML = "";
  for (const s of (r.subs || [])) {
    const tr = el("tr");
    tr.appendChild(cell(null, esc(s.name)));
    tr.appendChild(cell(null, "<span class='hint'>" + esc(s.url) + "</span>"));
    tr.appendChild(cell(null, String((s.node_ids || []).length)));
    tr.appendChild(cell(null, fmtTime(s.updated_at)));
    const cb = el("input");
    cb.type = "checkbox"; cb.checked = !!s.enabled;
    cb.onchange = async () => { await api("/api/subs/" + s.id, "PUT", { enabled: cb.checked }); refreshSubs(); };
    tr.appendChild(cell(cb));
    const ops = el("td");
    const bR = el("button", "sm ghost", "更新");
    bR.onclick = async () => {
      bR.textContent = "…";
      const t = await api("/api/subs/refresh", "POST", { id: s.id });
      bR.textContent = "更新";
      const res = t.result || {};
      msg("sub-msg", s.name + ": " + (res.ok === false ? "失败 " + (res.error || "") : "新增 " + (res.added ?? 0) + " / 更新 " + (res.updated ?? 0)), res.ok === false ? "err" : "ok");
      refreshSubs();
    };
    const bD = el("button", "sm danger", "删除");
    bD.onclick = async () => {
      if (!confirm("删除订阅 " + s.name + "（不删已导入节点）？")) return;
      await api("/api/subs/" + s.id, "DELETE");
      refreshSubs();
    };
    ops.appendChild(bR); ops.appendChild(bD);
    tr.appendChild(ops);
    tb.appendChild(tr);
  }
}
async function subImportAll() {
  const idEl = $("node-parse-msg");
  msg("node-parse-msg", "正在更新全部订阅…");
  const r = await api("/api/subs/refresh", "POST", {});
  const res = r.result || {};
  const results = res.results || [];
  if (r.ok && results.length) {
    msg("node-parse-msg", results.map(x => x.name + ": 新增 " + (x.added ?? 0) + "/更新 " + (x.updated ?? 0)).join("，"), "ok");
  } else if (r.ok) {
    msg("node-parse-msg", res.error || JSON.stringify(res), "ok");
  } else msg("node-parse-msg", r.error || "失败", "err");
  refreshNodes(); refreshSubs();
}

/* ---------------- 链式代理 ---------------- */
let CHAIN_PICKS = [];
function renderPicks(box, picks) {
  const order = {};
  picks.forEach((id, i) => order[id] = i + 1);
  let i = 0;
  for (const p of box.children) {
    if (!p.dataset || !p.dataset.id) continue;
    const id = p.dataset.id;
    p.classList.toggle("on", order[id] != null);
    const idx = p.querySelector(".idx");
    if (idx) idx.textContent = order[id] != null ? "#" + order[id] : String(++i);
  }
}
async function refreshChains() {
  const box = $("chain-member-picks");
  box.innerHTML = "";
  const nr = await api("/api/nodes");
  const nodes = (nr && nr.ok) ? (nr.nodes || []) : [];
  nodes.forEach((n, i) => {
    const p = el("span", "pick");
    p.dataset.id = n.id;
    p.appendChild(el("span", "idx", String(i + 1)));
    p.appendChild(el("span", null, n.name + " (" + n.type + ")"));
    p.onclick = () => {
      const at = CHAIN_PICKS.indexOf(n.id);
      if (at >= 0) CHAIN_PICKS.splice(at, 1);
      else CHAIN_PICKS.push(n.id);
      renderPicks(box, CHAIN_PICKS);
    };
    box.appendChild(p);
  });
  const bClear = el("button", "sm ghost", "清空选择");
  bClear.onclick = () => { CHAIN_PICKS = []; renderPicks(box, CHAIN_PICKS); };
  box.appendChild(bClear);
  renderPicks(box, CHAIN_PICKS);

  const r = await api("/api/chains");
  const list = $("chain-list");
  list.innerHTML = "";
  if (!r.ok) { list.appendChild(el("p", "hint", r.error || "加载失败")); return; }
  const chains = r.chains || [];
  if (!chains.length) list.appendChild(el("p", "hint", "还没有链。上方按顺序点选 ≥2 个节点：点选顺序 = 流量顺序，最后是出口。"));
  const nameOf = {};
  nodes.forEach(n => nameOf[n.id] = n.name);
  for (const c of chains) {
    const item = el("div", "chain-item");
    const head = el("div");
    head.appendChild(el("strong", null, c.name + (c.enabled ? "" : "（已禁用）")));
    if (c.note) head.appendChild(el("span", "hint", "  " + c.note));
    const cb = el("input");
    cb.type = "checkbox"; cb.checked = !!c.enabled;
    cb.onchange = async () => {
      await api("/api/chains/" + c.id, "PUT", { enabled: cb.checked });
      refreshChains(); refreshGroups();
    };
    head.appendChild(cb);
    const path = el("div", "path");
    const descs = c.describe || [];
    descs.forEach((d, i) => {
      if (i) path.appendChild(el("span", "arrow", "→"));
      path.appendChild(el("span", null, (i === descs.length - 1 ? "出口 " : "前置 " + (i + 1) + " ") + (nameOf[d] || d)));
    });
    item.appendChild(head);
    item.appendChild(path);
    const ops = el("div", "row");
    const bEg = el("button", "sm ghost", "出口IP测试");
    const pill = el("span", "pill", "");
    bEg.onclick = async () => {
      pill.textContent = "测试中…";
      const t = await api("/api/chains/" + c.id + "/egress", "POST", {});
      if (t.ok && t.ip) { pill.textContent = t.ip + " (" + t.ms + "ms)"; pill.className = "pill ok"; }
      else { pill.textContent = t.error || "失败"; pill.className = "pill off"; }
    };
    const bDel = el("button", "sm danger", "删除");
    bDel.onclick = async () => {
      if (!confirm("删除链 " + c.name + "？")) return;
      await api("/api/chains/" + c.id, "DELETE");
      refreshChains(); refreshGroups();
    };
    ops.appendChild(bEg); ops.appendChild(pill); ops.appendChild(bDel);
    item.appendChild(ops);
    list.appendChild(item);
  }
}
async function createChain() {
  const name = $("chain-name").value.trim();
  if (!name) { msg("chain-msg", "请输入链名称", "err"); return; }
  if (CHAIN_PICKS.length < 2) { msg("chain-msg", "至少选 2 个节点（第一个是前置，最后是出口）", "err"); return; }
  const r = await api("/api/chains", "POST", { name: name, members: CHAIN_PICKS });
  if (r.ok) {
    msg("chain-msg", "已创建: " + name, "ok");
    $("chain-name").value = "";
    CHAIN_PICKS = [];
    refreshChains(); refreshGroups();
  } else msg("chain-msg", r.error || "创建失败", "err");
}

/* ---------------- 节点组 ---------------- */
let GROUP_PICKS = [];
async function refreshGroups() {
  const box = $("group-member-picks");
  box.innerHTML = "";
  const nr = await api("/api/nodes");
  const cr = await api("/api/chains");
  const items = [];
  for (const n of ((nr && nr.ok) ? nr.nodes : [])) items.push({ id: n.id, label: n.name + " (" + n.type + ")" });
  for (const c of ((cr && cr.ok) ? cr.chains : [])) items.push({ id: c.id, label: "【链】" + c.name });
  items.forEach((it, i) => {
    const p = el("span", "pick");
    p.dataset.id = it.id;
    p.appendChild(el("span", "idx", String(i + 1)));
    p.appendChild(el("span", null, it.label));
    p.onclick = () => {
      const at = GROUP_PICKS.indexOf(it.id);
      if (at >= 0) GROUP_PICKS.splice(at, 1);
      else GROUP_PICKS.push(it.id);
      renderPicks(box, GROUP_PICKS);
    };
    box.appendChild(p);
  });
  const bClear = el("button", "sm ghost", "清空选择");
  bClear.onclick = () => { GROUP_PICKS = []; renderPicks(box, GROUP_PICKS); };
  box.appendChild(bClear);
  renderPicks(box, GROUP_PICKS);

  const r = await api("/api/groups");
  const list = $("group-list");
  list.innerHTML = "";
  if (!r.ok) { list.appendChild(el("p", "hint", r.error || "加载失败")); return; }
  const groups = r.groups || [];
  if (!groups.length) list.appendChild(el("p", "hint", "还没有组。成员顺序即 selector 的优先级顺序。"));
  const nameOf = {};
  items.forEach(it => nameOf[it.id] = it.label);
  for (const g of groups) {
    const item = el("div", "group-item");
    const head = el("div");
    head.appendChild(el("strong", null, g.name + (g.enabled ? "" : "（已禁用）")));
    head.appendChild(el("span", "pill", g.type));
    if (g.type === "urltest") head.appendChild(el("span", "pill", "间隔 " + (g.interval || 300) + "s / 容差 " + (g.tolerance || 50) + "ms"));
    const cb = el("input");
    cb.type = "checkbox"; cb.checked = !!g.enabled;
    cb.onchange = async () => {
      await api("/api/groups/" + g.id, "PUT", { enabled: cb.checked });
      refreshGroups();
    };
    head.appendChild(cb);
    const path = el("div", "path");
    (g.members || []).forEach((d, i) => {
      if (i) path.appendChild(el("span", "arrow", "→"));
      path.appendChild(el("span", null, nameOf[d] || d));
    });
    if (g.default) path.appendChild(el("span", "pill ok", "默认: " + (nameOf[g.default] || g.default)));
    item.appendChild(head);
    item.appendChild(path);
    const ops = el("div", "row");
    const bDel = el("button", "sm danger", "删除");
    bDel.onclick = async () => {
      if (!confirm("删除组 " + g.name + "？")) return;
      await api("/api/groups/" + g.id, "DELETE");
      refreshGroups();
    };
    ops.appendChild(bDel);
    item.appendChild(ops);
    list.appendChild(item);
  }
}
async function createGroup() {
  const name = $("group-name").value.trim();
  const type = $("group-type").value;
  if (!name) { msg("group-msg", "请输入组名", "err"); return; }
  if (GROUP_PICKS.length < 1) { msg("group-msg", "至少选 1 个成员", "err"); return; }
  const r = await api("/api/groups", "POST", { name: name, type: type, members: GROUP_PICKS });
  if (r.ok) {
    msg("group-msg", "已创建: " + name, "ok");
    $("group-name").value = "";
    GROUP_PICKS = [];
    refreshGroups();
  } else msg("group-msg", r.error || "创建失败", "err");
}

/* ---------------- 分流规则 ---------------- */
let EXTRA_RULES = [];
async function refreshRules() {
  const r = await api("/api/settings");
  if (!r.ok) return;
  EXTRA_RULES = (r.settings.extra_rules || []).slice();
  const nc = await api("/api/nodes");
  const ch = await api("/api/chains");
  const gr = await api("/api/groups");
  const names = ["直连", "拦截", "自动选择"];
  for (const n of ((nc && nc.ok) ? nc.nodes : [])) names.push(n.name);
  for (const c of ((ch && ch.ok) ? ch.chains : [])) names.push(c.name);
  for (const g of ((gr && gr.ok) ? gr.groups : [])) names.push(g.name);
  const sel = $("cr-out");
  const cur = sel.value;
  sel.innerHTML = "";
  for (const nm of names) {
    const o = el("option", null, nm);
    o.value = nm;
    sel.appendChild(o);
  }
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
  renderCrList();
}
function renderCrList() {
  const box = $("cr-list");
  box.innerHTML = "";
  if (!EXTRA_RULES.length) { box.appendChild(el("div", "hint", "暂无自定义规则。")); return; }
  EXTRA_RULES.forEach((r, i) => {
    const d = el("div", "rule-item");
    const head = el("div");
    head.appendChild(el("span", "pill", r.type || "domain"));
    head.appendChild(el("span", null, String(r.value || "")));
    head.appendChild(el("span", "pill", "→ " + (r.outbound || "")));
    if (r.enabled === false) head.appendChild(el("span", "pill off", "已停用"));
    const bDel = el("button", "sm danger", "删除");
    bDel.onclick = async () => {
      const next = EXTRA_RULES.filter((_, j) => j !== i);
      const u = await api("/api/settings", "POST", { extra_rules: next });
      if (u.ok) refreshRules();
      else alert(u.error || "删除失败");
    };
    head.appendChild(bDel);
    d.appendChild(head);
    box.appendChild(d);
  });
}
async function addCustomRule() {
  const type = $("cr-type").value;
  const value = $("cr-value").value.trim();
  const outbound = $("cr-out").value;
  if (!value) { alert("请输入规则值"); return; }
  if (!outbound) { alert("请选择出口"); return; }
  EXTRA_RULES.push({ type: type, value: value, outbound: outbound, enabled: true });
  const u = await api("/api/settings", "POST", { extra_rules: EXTRA_RULES });
  if (u.ok) { $("cr-value").value = ""; refreshRules(); }
  else alert(u.error || "添加失败");
}

/* ---------------- 设置 ---------------- */
const FIELDS = {
  "form-core": [
    ["core_binary", "内核二进制路径", "text"],
    ["log_level", "日志级别", "select:info,warn,error,debug"],
    ["auto_start_core", "面板启动时自动启动内核", "cb"],
    ["tun_enabled", "TUN 透明代理", "cb"],
    ["tun_interface", "TUN 接口名", "text"],
    ["tun_address", "TUN 地址", "text"],
    ["tun_stack", "TUN 协议栈", "select:system,gvisor,mixed"],
    ["tun_auto_route", "auto_route", "cb"],
    ["tun_strict_route", "strict_route", "cb"],
    ["tun_dns_mode", "TUN DNS 模式", "select:hijack,native,disabled"],
    ["mixed_enabled", "Mixed 代理入站", "cb"],
    ["mixed_listen", "Mixed 监听地址", "text"],
    ["mixed_port", "Mixed 端口", "int"],
  ],
  "form-dns": [
    ["dns_mode", "DNS 模式", "select:fakeip,auto"],
    ["dns_local_servers", "本地 DNS（每行一个）", "textarea"],
    ["dns_overseas_servers", "海外 DNS（每行一个，走代理）", "textarea"],
    ["dns_fakeip_pool", "FakeIP 地址池", "text"],
    ["dns_strategy", "DNS 策略", "select:prefer_ipv4,prefer_ipv6,ipv4_only,ipv6_only"],
  ],
  "form-route": [
    ["route_mode", "分流模式", "select:proxy,global,custom,direct"],
    ["final_outbound", "最终出口（custom 模式）", "select-dynamic"],
    ["block_ads", "拦截广告", "cb"],
  ],
  "form-panel": [
    ["panel_port", "面板端口", "int"],
    ["panel_listen", "面板监听地址", "text"],
    ["sub_update_interval", "订阅更新间隔（小时）", "int"],
    ["geo_url_base", "Geo 下载源 base", "text"],
    ["rule_set_url_base", "Rule-set 下载源 base", "text"],
  ],
};
async function refreshSettings() {
  const r = await api("/api/settings");
  if (!r.ok) return;
  const s = r.settings;
  const nc = await api("/api/nodes");
  const ch = await api("/api/chains");
  const gr = await api("/api/groups");
  const names = ["auto"];
  for (const n of ((nc && nc.ok) ? nc.nodes : [])) names.push(n.name);
  for (const c of ((ch && ch.ok) ? ch.chains : [])) names.push(c.name);
  for (const g of ((gr && gr.ok) ? gr.groups : [])) names.push(g.name);
  for (const [formId, fields] of Object.entries(FIELDS)) {
    const box = $(formId);
    if (!box) continue;
    box.innerHTML = "";
    for (const [key, label, kind] of fields) {
      const row = el("div");
      row.className = "form-row";
      const lab = el("label", null, label);
      const div = el("div");
      let inp;
      if (kind === "cb") {
        inp = el("input");
        inp.type = "checkbox";
        inp.checked = !!s[key];
      } else if (kind === "select-dynamic") {
        inp = el("select");
        const o0 = el("option", null, "自动（主选择组）");
        o0.value = "auto";
        inp.appendChild(o0);
        for (const nm of names.slice(1)) {
          const o = el("option", null, nm);
          o.value = nm;
          inp.appendChild(o);
        }
        const want = s[key] || "auto";
        if (![...inp.options].some(o => o.value === want)) {
          const o = el("option", null, want);
          o.value = want;
          inp.appendChild(o);
        }
        inp.value = want;
      } else if (kind.indexOf("select:") === 0) {
        inp = el("select");
        for (const o of kind.slice(7).split(",").filter(Boolean)) {
          const oe = el("option", null, o);
          oe.value = o;
          inp.appendChild(oe);
        }
        inp.value = s[key];
      } else if (kind === "textarea") {
        inp = el("textarea");
        inp.rows = 3;
        inp.value = (s[key] || []).join("\n");
      } else {
        inp = el("input");
        inp.value = s[key] == null ? "" : s[key];
        if (kind === "int") inp.type = "number";
      }
      inp.dataset.key = key;
      div.appendChild(inp);
      row.appendChild(lab);
      row.appendChild(div);
      box.appendChild(row);
    }
  }
}
async function saveSettings() {
  const out = {};
  for (const fields of Object.values(FIELDS)) {
    for (const [key, , kind] of fields) {
      const inp = document.querySelector('[data-key="' + key + '"]');
      if (!inp) continue;
      let v;
      if (kind === "cb") v = inp.checked;
      else if (kind === "int") v = parseInt(inp.value, 10);
      else if (kind === "textarea") v = inp.value.split("\n").map(x => x.trim()).filter(Boolean);
      else v = inp.value;
      out[key] = v;
    }
  }
  const r = await api("/api/settings", "POST", out);
  msg("settings-msg", r.ok ? "已保存。可到「状态」页点「校验配置」验证。" : (r.error || "保存失败"), r.ok ? "ok" : "err");
}
async function changePassword() {
  const old = prompt("当前密码（从未改过则输入 pr-sing）", "pr-sing");
  if (old === null) return;
  const nw = prompt("新密码（至少 4 位）");
  if (nw === null) return;
  const r = await api("/api/password", "POST", { old: old, password: nw });
  msg("settings-msg", r.ok ? "密码已修改，请用新密码重新登录。" : (r.error || "修改失败"), r.ok ? "ok" : "err");
}

/* ---------------- 事件绑定与初始化 ---------------- */
function bindEvents() {
  const b = (id, fn) => { const e = $(id); if (e) e.addEventListener("click", fn); };
  b("login-btn", doLogin);
  const pw = $("login-pw");
  if (pw) pw.addEventListener("keydown", e => { if (e.key === "Enter") doLogin(); });
  b("logout", () => { TOKEN = ""; localStorage.removeItem("prsing_token"); showLogin(); });
  document.querySelectorAll("nav button").forEach(bt => bt.addEventListener("click", () => switchTab(bt.dataset.tab)));
  b("btn-core-start", () => coreAction("start"));
  b("btn-core-stop", () => coreAction("stop"));
  b("btn-core-restart", () => coreAction("restart"));
  b("btn-core-regen", coreRegen);
  b("btn-log-refresh", refreshLogs);
  b("btn-rules-update", async () => {
    const e = $("btn-rules-update");
    e.textContent = "更新中…";
    const r = await api("/api/rules/update", "POST", {});
    e.textContent = "更新规则库";
    alert(r.ok ? "规则库更新完成" : (r.error || "更新失败"));
    refreshStatus();
  });
  b("btn-node-parse", parseLinks);
  b("btn-node-import", importLinks);
  b("btn-sub-import", subImportAll);
  b("btn-sub-add", async () => {
    const r = await api("/api/subs", "POST", { name: $("sub-name").value, url: $("sub-url").value.trim() });
    if (r.ok) { msg("sub-msg", "已添加，点「更新」拉取节点。", "ok"); $("sub-name").value = ""; $("sub-url").value = ""; refreshSubs(); }
    else msg("sub-msg", r.error || "失败", "err");
  });
  b("btn-sub-refresh-all", subImportAll);
  b("btn-chain-add", createChain);
  b("btn-group-add", createGroup);
  b("btn-cr-add", addCustomRule);
  b("btn-settings-save", saveSettings);
  b("btn-pw", changePassword);
  const modal = $("modal");
  if (modal) modal.addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
}
function init() {
  bindEvents();
  refreshLogs();
  api("/api/status").then(r => { if (r.ok) showApp(); else showLogin(); });
}
document.addEventListener("DOMContentLoaded", () => { setTimeout(init, 100); });

/* Local-only UI. All mutations go through the same guarded Python core as CLI. */
"use strict";
const $ = (selector, scope = document) => scope.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const kindNames = {rule:"常驻规则", skill:"流程技能", template:"文档模板"};
const kindIcons = {rule:"⌘", skill:"⌁", template:"▤"};
const S = {data:null, page:"library", filter:"all", query:"", edit:null, dirty:false, wizard:null, modalAction:null, busy:false};
const md = window.markdownit ? window.markdownit({html:false, linkify:false, breaks:false}) : null;
// Preview never retrieves remote or local file images from user-authored Markdown.
if (md) md.renderer.rules.image = (tokens, index) => `<span class="muted">[图片：${esc(tokens[index].content)}]</span>`;
const markdown = text => md ? md.render(text) : `<pre>${esc(text)}</pre>`;

async function api(path, data) {
  const options = data === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json", "X-BP-Token":S.data.token}, body:JSON.stringify(data)};
  const response = await fetch(path, options);
  let result;
  try { result = await response.json(); } catch { throw new Error("服务响应异常，请检查终端中的本地服务"); }
  if (!response.ok) throw new Error(result.error || `请求失败 (${response.status})`);
  return result;
}
function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show${error ? " error" : ""}`;
  clearTimeout(S.toastTimer);
  S.toastTimer = setTimeout(() => element.classList.remove("show"), error ? 7000 : 4000);
}
async function reload(render = true) {
  S.data = await api("/api/state");
  $("#nav-count").textContent = S.data.catalog.length;
  $("#footer-version").textContent = `规范版本 ${S.data.releases.at(-1)?.version || "尚未创建"}`;
  if (render) renderPage();
}
function latest() { return S.data.releases.at(-1)?.version; }
function project(id) { return S.data.projects.find(p => p.id === id); }
function head(eyebrow, title, subtitle, action = "") {
  return `<div class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="subtitle">${subtitle}</p></div>${action}</div>`;
}
function diffs(changes) {
  if (!changes.length) return '<div class="notice success">没有需要写入的变更。</div>';
  return changes.map(c => `<details class="diff-file"><summary>${esc(c.path)}<span>${esc(c.action || "变更")}</span></summary><pre class="diff">${(c.diff || "").split("\n").map(line => `<span class="diff-line ${line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : ""}">${esc(line)}</span>`).join("")}</pre></details>`).join("");
}
function notice(text, error = false) { return `<div class="notice${error ? " error" : ""}">${esc(text)}</div>`; }
function renderPage() {
  const names = {library:"规范库", editor:"规范编辑", projects:"项目管理", versions:"版本管理", guide:"使用指南"};
  $("#breadcrumb").textContent = names[S.page] || names.library;
  document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("active", a.dataset.nav === (S.page === "editor" ? "library" : S.page)));
  ({library:renderLibrary, editor:renderEditor, projects:renderProjects, versions:renderVersions, guide:renderGuide}[S.page] || renderLibrary)();
}
function renderLibrary() {
  const items = S.data.catalog.filter(i => (S.filter === "all" || i.kind === S.filter) && `${i.title} ${i.id} ${i.description} ${i.body}`.toLowerCase().includes(S.query.toLowerCase()));
  const count = kind => S.data.catalog.filter(i => i.kind === kind).length;
  $("#main").innerHTML = head("STANDARDS LIBRARY", "规范库", "让规则清晰，让协作有据可循。统一维护，可在不同项目中复用。", '<button class="button primary" data-action="new">＋ 新建规范</button>') +
    `<div class="banner"><div><div class="banner-label">BUILD ON GOOD PRACTICE</div><h2>一套规范，贯穿完整研发流程</h2><p>从需求到交付，按需使用；从一个项目，到每一个项目。</p></div><a class="banner-link" href="#projects">接入项目 <span>↗</span></a></div>
    <div class="stats">${[["规范总数",S.data.catalog.length,"项","▦"],["常驻规则",count("rule"),"项","⌘"],["流程技能",count("skill"),"个","⌁"],["文档模板",count("template"),"份","▤"]].map(([name,n,unit,icon]) => `<div class="stat"><div><div class="stat-name">${name}</div><div class="stat-number">${n}<small>${unit}</small></div></div><span class="stat-icon">${icon}</span></div>`).join("")}</div>
    <div class="toolbar"><div class="tabs" role="group" aria-label="规范分类">${[["all","全部规范",S.data.catalog.length],...["rule","skill","template"].map(k=>[k,kindNames[k],count(k)])].map(([id,name,n])=>`<button class="tab ${S.filter===id?"active":""}" data-action="filter" data-id="${id}">${name}<span>${n}</span></button>`).join("")}</div><label class="search"><input id="search" type="search" aria-label="搜索规范" placeholder="搜索名称、标识或内容…" value="${esc(S.query)}"></label></div>
    <div class="section-line"><strong>${S.filter === "all" ? "全部规范" : kindNames[S.filter]}</strong><span>共 ${items.length} 项 · 草稿工作区</span></div>
    <div class="cards">${items.map(i => `<article class="card"><div class="card-top"><span class="item-icon ${i.kind}">${kindIcons[i.kind]}</span><span class="badge ${i.enabled?"":"off"}">${i.enabled?"已启用":"已停用"}</span></div><h3>${esc(i.title)}</h3><div class="card-id">${esc(i.id)}</div><p>${esc(i.description || i.body.replace(/[#\-*`]/g, "").trim().slice(0,80))}</p><div class="card-foot"><span>${kindNames[i.kind]}</span><button class="text-button" data-action="edit" data-id="${i.id}">查看与编辑 <span>↗</span></button></div></article>`).join("") || '<div class="empty">没有匹配的规范，试试其他关键词。</div>'}</div>`;
}
function renderEditor() {
  const i = S.edit;
  $("#main").innerHTML = `<button class="back" data-action="back">← 返回规范库</button>` + head("STANDARD EDITOR", i.etag ? "编辑规范" : "新建规范", "修改先保存为草稿；创建新版本后，项目可按需升级。", '<button class="button primary" type="submit" form="editor-form">预览并保存</button>') +
    `<form id="editor-form"><div class="editor-layout"><div class="panel"><label class="field">规范名称<input name="title" required maxlength="120" value="${esc(i.title)}"></label><label class="field">唯一标识<input name="id" required pattern="[a-z][a-z0-9]*(?:-[a-z0-9]+)*" maxlength="63" ${i.etag?"readonly":""} value="${esc(i.id)}"><small>小写英文、数字与连字符；创建后保持稳定。</small></label><label class="field">规范类型<select name="kind" ${i.etag?"disabled":""}>${Object.entries(kindNames).map(([key,name])=>`<option value="${key}" ${i.kind===key?"selected":""}>${name}</option>`).join("")}</select></label><label class="field">用途与触发描述<textarea name="description" maxlength="1024">${esc(i.description)}</textarea><small>技能描述用于判断何时调用，请清晰限定用途。</small></label><label class="checkbox"><input type="checkbox" name="enabled" ${i.enabled?"checked":""}>在新版本中启用</label><div class="notice">停用不会改变已接入的项目。项目升级并确认后才生效。</div><span class="saved-hint" id="dirty-label">${i.etag?"已加载本地草稿":"尚未保存"}</span></div><div class="editor-main"><section class="editor-pane"><div class="pane-title">MARKDOWN <span>规范正文</span></div><textarea aria-label="规范正文" class="code-editor" name="body" required spellcheck="false">${esc(i.body)}</textarea></section><section class="editor-pane"><div class="pane-title">PREVIEW <span>实时预览</span></div><div class="markdown" id="md-preview">${markdown(i.body)}</div></section></div></div></form>`;
}
function renderProjects() {
  $("#main").innerHTML = head("PROJECT WORKSPACE", "项目管理", "将规范接入本地项目，独立配置、固定版本、按需升级。") +
    `<section class="panel"><div class="panel-head"><div><h2>接入一个项目</h2><p>先登记已有目录；登记不会修改项目文件。</p></div><span class="badge">跨技术栈</span></div><form id="register-form" class="form-row"><label class="field">本地项目路径<input name="path" required placeholder="例如 C:\\Projects\\my-app 或 /Users/me/projects/my-app"></label><button class="button primary" type="submit">登记项目 ＋</button></form></section>` +
    (S.data.projects.length ? S.data.projects.map(p=>`<section class="panel"><div class="row between"><h2>${esc(p.status.config?.project_name || p.name)}</h2><span class="badge ${p.status.ok?"":"warn"}">${p.status.installed ? p.status.ok?"已接入":"需要处理" : "待接入"}</span></div><div class="project-path">${esc(p.path)}</div><div class="project-info"><span>当前版本 <strong>${esc(p.status.version || "—")}</strong></span><span>最新版本 ${esc(latest() || "—")}</span><span>${esc(p.status.config?.stack?.join(" / ") || "技术栈待配置")}</span></div>${p.status.installed && p.status.issues?.length ? p.status.issues.map(i=>notice(i,true)).join("") : ""}${(p.status.notes||[]).map(i=>notice(i)).join("")}<div class="project-actions">${p.status.installed ? `<button class="button small" data-action="configure" data-id="${p.id}">修改配置</button><button class="button small primary" data-action="upgrade" data-id="${p.id}">预览升级 ↗</button>` : `<button class="button small primary" data-action="quick" data-id="${p.id}">一键确认接入 ↗</button><button class="button small" data-action="guided" data-id="${p.id}">引导设置</button>`}<button class="button small" data-action="check" data-id="${p.id}">检查状态</button></div></section>`).join("") : '<div class="empty"><h2>让第一个项目用上好规范</h2><p>在上方填写项目路径，即可预览接入内容。</p></div>');
}
function renderVersions() {
  const changes = S.data.draft_diff;
  $("#main").innerHTML = head("VERSION CONTROL", "版本管理", "草稿自由修改，版本保持稳定。每个项目由你决定何时更新。") +
    `<section class="panel"><div class="panel-head"><div><h2>当前草稿</h2><p>相比 ${esc(latest() || "空规范库")} 有 ${changes.length} 个文件变化。</p></div><span class="badge ${changes.length?"warn":""}">${changes.length?"有未发布修改":"与最新版本一致"}</span></div>${diffs(changes)}<form id="release-form" class="form-row"><label class="field">新版本号<input name="version" pattern="[0-9]+\.[0-9]+\.[0-9]+" required value="${esc(S.data.next_version)}"></label><button class="button primary" ${!changes.length?"disabled":""}>创建规范版本 ↗</button></form><p class="muted">创建本地版本快照，不会提交 Git、上传云端或升级其他项目。</p></section><section class="panel"><h2>版本历史</h2>${S.data.releases.slice().reverse().map((r,n)=>`<div class="version-row"><div><div class="row"><span class="version-name">v${esc(r.version)}</span>${n===0?'<span class="badge">最新版本</span>':""}</div><div class="version-meta">${esc(new Date(r.created_at).toLocaleString("zh-CN"))} · ${r.items} 项规范 · 不可覆盖</div></div><button class="button small" data-action="version" data-id="${r.version}">查看版本</button></div>`).join("") || '<div class="empty">尚无版本，请创建首个版本。</div>'}</section>`;
}
function setupPrompt() {
  return `请读取 ${S.data.toolkit_path}/.agents/skills/bp-setup/SKILL.md，为当前项目接入 Codex Best Practice。使用推荐配置，先展示实际文件差异，再由我一次确认后应用。保留已有规则与本地修改。`;
}
function renderGuide() {
  $("#main").innerHTML = head("GETTING STARTED", "把规范带到其他项目", "从一句提示词开始；项目接入之后，即可按需调用流程技能。") +
    `<div class="guide-grid"><section class="panel"><div class="guide-step">01 / 在 CODEX 对话中使用</div><h2>复制提示词，接入当前项目</h2><p>在另一个项目打开 Codex，把下面这段话发给它。工具仓库需保留在本机。</p><pre class="copy-block">${esc(setupPrompt())}</pre><button class="button primary" data-action="copy-prompt">复制接入提示词 ↗</button></section><section class="panel"><div class="guide-step">02 / 在管理台中使用</div><h2>选择最适合你的设置方式</h2><p>项目管理中填写目录后，可直接采用推荐配置，或通过引导逐项调整。先看差异，再确认写入。</p><div class="notice">未知验证命令保持待补充。自动识别的命令默认待确认；设置过程不会执行项目命令。</div><a href="#projects" class="button">前往项目管理 ↗</a></section><section class="panel"><div class="guide-step">03 / 日常开发</div><h2>按任务调用，不增加多余流程</h2><div class="markdown">${markdown("- `$bp-plan`：复杂需求与任务计划\n- `$bp-implement`：实现与验证\n- `$bp-review`：变更评审\n- `$bp-handoff`：交付与长任务交接\n- `$bp-retro`：基于证据改进规范\n\n小任务可直接描述目标，不必逐个调用技能。")}</div></section><section class="panel"><div class="guide-step">04 / 后续升级</div><h2>规范变好，项目按需跟进</h2><p>规范库编辑 → 保存草稿 → 创建新版本 → 项目管理中预览升级 → 确认应用。</p><div class="notice">已有 AGENTS.md 保留受管区块外内容。受管文件被本地修改时，工具会停止升级并展示冲突。</div><p>完整说明见仓库 README.md 与 BEST_PRACTICES.md。</p></section></div>`;
}
function dialog(title, subtitle, body, buttons, action) {
  S.modalAction = action || null;
  $("#modal-content").innerHTML = `<div class="modal-head"><div><h2 id="modal-title">${esc(title)}</h2><p>${esc(subtitle)}</p></div><button class="icon-button" data-action="close" aria-label="关闭">×</button></div><div class="modal-body">${body}</div><div class="modal-foot">${buttons || '<button class="button" data-action="close">关闭</button>'}</div>`;
  if (!$("#modal").open) $("#modal").showModal();
}
function closeDialog() { $("#modal").close(); S.modalAction = null; }
function readEditor() {
  const f = new FormData($("#editor-form"));
  return {id:f.get("id"), title:f.get("title"), kind:f.get("kind") || S.edit.kind, description:f.get("description"), enabled:f.has("enabled"), body:f.get("body"), etag:S.edit.etag};
}
function editorDiff(before, after) {
  if (before === after) return "正文未改变；请检查上方元信息变更。";
  return [...before.split("\n").map(l=>"-"+l), ...after.split("\n").map(l=>"+"+l)].join("\n");
}
function previewSave() {
  const data = readEditor();
  if (data.kind === "skill" && !data.description.trim()) return toast("Skill 描述不能为空", true);
  dialog("保存规范草稿", "仅修改规范库草稿，已接入项目保持原版本。", `<div class="summary-grid"><span>规范</span><strong>${esc(data.title)} · ${esc(data.id)}</strong><span>类型</span><strong>${kindNames[data.kind]}</strong><span>状态</span><strong>${data.enabled?"启用":"停用"}</strong><span>触发描述</span><strong>${esc(data.description || "—")}</strong></div>${diffs([{path:"规范正文", diff:editorDiff(S.edit.body || "", data.body)}])}`, '<button class="button" data-action="close">继续编辑</button><button class="button primary" data-action="confirm">确认保存草稿</button>', async()=>{
    const item = await api("/api/catalog", data);
    S.edit = item; S.dirty = false;
    closeDialog(); await reload(); toast("草稿已保存。创建新版本后即可用于项目升级。");
  });
}
async function startSetup(id, mode, operation) {
  const p = project(id);
  if (!latest()) throw new Error("请先在版本管理中创建规范版本");
  const version = operation === "configure" ? p.status.version : latest();
  const snapshot = await api(`/api/releases/${version}`);
  const detected = p.status.installed ? p.status.config : await api("/api/detect", {project_id:id});
  const active = snapshot.manifest.catalog.filter(i=>i.enabled);
  const settings = {...detected, enabled_ids:detected.enabled_ids?.filter(i=>active.some(a=>a.id===i)) || active.map(i=>i.id)};
  delete settings.notes;
  S.wizard = {id, operation, version, step:0, settings:structuredClone(settings), catalog:active};
  if (mode === "quick") await previewProject(null);
  else renderWizard();
}
function collectWizard() {
  const form = $("#wizard-form");
  if (!form) return;
  const f = new FormData(form), w = S.wizard;
  if (w.step === 0) {
    w.settings.project_name = String(f.get("project_name") || "");
    w.settings.stack = String(f.get("stack") || "").split(/[,，\n]/).map(s=>s.trim()).filter(Boolean);
  } else if (w.step === 1) {
    w.settings.checks = [...form.querySelectorAll(".check-row")].map((el,n)=>({name:String(f.get(`name-${n}`)||""), command:String(f.get(`command-${n}`)||""), confirmed:f.has(`confirmed-${n}`)})).filter(c=>c.name || c.command);
  } else if (w.step === 2) w.settings.boundaries = String(f.get("boundaries")||"").split("\n").map(s=>s.trim()).filter(Boolean);
  else w.settings.enabled_ids = f.getAll("enabled");
}
function renderWizard() {
  const w=S.wizard, c=w.settings;
  let content="";
  if (w.step===0) content=`<label class="field">项目名称<input name="project_name" required value="${esc(c.project_name)}"></label><label class="field">技术栈<input name="stack" value="${esc(c.stack.join(", "))}" placeholder="例如 TypeScript, React 或 Python"><small>用逗号分隔；可留空，后续再补充。</small></label>`;
  if (w.step===1) content=`<p class="muted">勾选“已核实”表示已确认命令入口，不表示已经运行或通过。</p>${c.checks.map((check,n)=>`<div class="check-row"><label class="field">名称<input name="name-${n}" required value="${esc(check.name)}"></label><label class="field">命令<input name="command-${n}" required value="${esc(check.command)}"></label><label class="checkbox"><input type="checkbox" name="confirmed-${n}" ${check.confirmed?"checked":""}>已核实</label></div>`).join("") || notice("尚无验证命令，可以留空。日常任务中按实际情况补充。") }<button type="button" class="button small" data-action="add-check">＋ 添加命令</button>`;
  if (w.step===2) content=`<label class="field">修改边界与项目约定<textarea name="boundaries" rows="7" placeholder="每行一条，例如：数据库迁移需要先说明兼容方案">${esc(c.boundaries.join("\n"))}</textarea><small>这是代理应遵守的文字约定，不替代运行环境权限。</small></label>`;
  if (w.step===3) content=`<div class="check-options">${w.catalog.map(i=>`<label class="checkbox"><input type="checkbox" name="enabled" value="${i.id}" ${c.enabled_ids.includes(i.id)?"checked":""}><span>${esc(i.title)}<small>${kindNames[i.kind]}</small></span></label>`).join("")}</div>`;
  dialog(w.operation==="configure"?"修改项目配置":"引导设置", `${project(w.id).name} · 规范版本 ${w.version}`, `<div class="steps">${["项目信息","验证命令","修改边界","启用规范"].map((name,n)=>`<span class="step ${n===w.step?"active":""}"><b>${n+1}</b>${name}</span>`).join("")}</div><form id="wizard-form">${content}</form>`, `<button class="button" data-action="${w.step?"previous-step":"close"}">${w.step?"上一步":"取消"}</button><button class="button primary" data-action="next-step">${w.step===3?"预览文件差异 ↗":"下一步 →"}</button>`);
}
async function previewProject(settings) {
  const w = S.wizard;
  const plan = await api("/api/plans", {project_id:w.id, operation:w.operation, version:w.version, settings});
  const checks=plan.config.checks;
  const summary=`<div class="summary-grid"><span>目标项目</span><strong>${esc(plan.config.project_name)}</strong><span>目录</span><strong>${esc(plan.target)}</strong><span>规范版本</span><strong>${esc(plan.version)}</strong><span>技术栈</span><strong>${esc(plan.config.stack.join(" / ") || "待补充")}</strong><span>文件变更</span><strong>${plan.changes.length} 项</strong><span>验证命令</span><strong>${checks.length ? checks.map(c=>`${esc(c.command)} ${c.confirmed?"（已核实）":"（待确认）"}`).join("<br>") : "待补充"}</strong></div>`;
  dialog(plan.operation==="upgrade"?"确认规范升级":plan.operation==="configure"?"确认配置变更":"确认接入项目", "预览不会修改项目。请检查以下实际差异后确认一次。", summary + (checks.some(c=>!c.confirmed)||!checks.length?notice("验证命令尚未完整核实；接入过程不会执行这些命令。建议在实际开发时结合项目清单确认。 "):"") + plan.conflicts.map(c=>notice(c,true)).join("") + diffs(plan.changes), `<button class="button" data-action="close">取消</button><button class="button" data-action="wizard-from-preview">调整设置</button><button class="button primary" data-action="confirm" ${plan.conflicts.length?"disabled":""}>${plan.conflicts.length?"请先处理冲突":plan.changes.length?"确认应用":"确认 · 已是当前配置"}</button>`, async()=>{
    const result = await api(`/api/plans/${plan.id}/apply`, {});
    closeDialog(); await reload(); toast(`已完成，规范版本 ${result.version}，变更 ${result.changed} 个文件。`);
  });
  w.settings = structuredClone(plan.config);
}
async function showVersion(version) {
  const result = await api(`/api/releases/${version}`);
  dialog(`规范版本 ${version}`, "不可变快照；下方展示当前草稿相对该版本的差异。", `<div class="summary-grid"><span>创建时间</span><strong>${esc(new Date(result.manifest.created_at).toLocaleString("zh-CN"))}</strong><span>规范数量</span><strong>${result.manifest.catalog.length}</strong></div><div class="row wrap">${result.manifest.catalog.map(i=>`<span class="badge ${i.enabled?"":"off"}">${esc(i.title)}</span>`).join("")}</div>${diffs(result.diff)}`, '<button class="button" data-action="close">关闭</button><button class="button primary" data-action="confirm">复制为新草稿…</button>', ()=>{
    const hash=S.data.catalog_hash;
    dialog("将历史版本复制为草稿", "会替换当前草稿内容；历史版本和已接入项目保持原样。", diffs(result.diff), '<button class="button" data-action="close">取消</button><button class="button primary" data-action="confirm">确认替换当前草稿</button>', async()=>{
      await api("/api/restore",{version,catalog_hash:hash}); closeDialog(); await reload(); toast("历史内容已复制到草稿，可继续编辑并创建新版本。");
    });
  });
}
document.addEventListener("click", async event=>{
  const button=event.target.closest("[data-action]");
  if (!button || S.busy) return;
  const {action,id}=button.dataset;
  try {
    if (action==="new" || action==="edit") {
      if (S.dirty && !confirm("有未保存的规范修改，确定离开吗？")) return;
      S.edit=action==="edit"?structuredClone(S.data.catalog.find(i=>i.id===id)):{id:"",title:"",description:"",body:"# 新规范\n\n描述这项规范的适用条件与具体行为。\n",kind:"rule",enabled:true};
      S.page="editor";S.dirty=false;renderPage();
    } else if(action==="back") navigate("library");
    else if(action==="filter") {S.filter=id;renderLibrary();}
    else if(action==="close") closeDialog();
    else if(action==="confirm" && S.modalAction) {
      S.busy=true;button.disabled=true;await S.modalAction();
    } else if(["quick","guided","configure","upgrade"].includes(action)) {
      await startSetup(id,action==="guided"||action==="configure"?"guided":"quick",action==="upgrade"?"upgrade":action==="configure"?"configure":"init");
    } else if(action==="check") {await reload();const p=project(id);toast(p.status.ok?`检查通过，当前版本 ${p.status.version}${p.status.notes?.length?"；部分配置待补充":""}`:p.status.issues.join("；"),!p.status.ok);}
    else if(action==="add-check") {collectWizard();S.wizard.settings.checks.push({name:"",command:"",confirmed:false});renderWizard();}
    else if(action==="next-step") {
      if(!$("#wizard-form").reportValidity())return;
      collectWizard();if(S.wizard.step===3)await previewProject(S.wizard.settings);else{S.wizard.step++;renderWizard();}
    } else if(action==="previous-step") {collectWizard();S.wizard.step--;renderWizard();}
    else if(action==="wizard-from-preview") {S.wizard.step=0;renderWizard();}
    else if(action==="version") await showVersion(id);
    else if(action==="copy-prompt") {await navigator.clipboard.writeText(setupPrompt());toast("提示词已复制，可发送到另一个项目的 Codex 对话。");}
  } catch(error){toast(error.message,true);} finally{S.busy=false; if(button.isConnected && action==="confirm")button.disabled=false;}
});
document.addEventListener("submit", async event=>{
  event.preventDefault();
  if(S.busy)return;
  const formId = event.target.getAttribute("id");
  try {
    if(formId==="editor-form") previewSave();
    if(formId==="register-form") {
      S.busy=true;await api("/api/projects",{path:new FormData(event.target).get("path")});await reload();toast("目录已登记，项目文件尚未修改。");
    }
    if(formId==="release-form") {
      const version=new FormData(event.target).get("version"), hash=S.data.catalog_hash;
      dialog(`创建版本 ${version}`, "保存完整、不可覆盖的本地规范快照。不会自动更新任何项目。",diffs(S.data.draft_diff),'<button class="button" data-action="close">取消</button><button class="button primary" data-action="confirm">确认创建版本</button>',async()=>{await api("/api/releases",{version,catalog_hash:hash});closeDialog();await reload();toast(`规范版本 ${version} 已创建。`);});
    }
  } catch(error){toast(error.message,true);}finally{S.busy=false;}
});
document.addEventListener("input", event=>{
  if(event.target.id==="search") {
    const start=event.target.selectionStart;S.query=event.target.value;renderLibrary();$("#search").focus();if(start!==null)$("#search").setSelectionRange(start,start);
  }
  if(event.target.closest("#editor-form")) {
    S.dirty=true;$("#dirty-label").textContent="有未保存修改";
    if(event.target.name==="body")$("#md-preview").innerHTML=markdown(event.target.value);
  }
});
function navigate(page) {
  if(S.dirty && !confirm("有未保存的规范修改，确定离开吗？"))return;
  S.dirty=false;S.page=["library","projects","versions","guide"].includes(page)?page:"library";renderPage();
}
document.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener("click",event=>{event.preventDefault();if(S.data)navigate(a.hash.slice(1));}));
// Delegated links cover content that was rendered after startup.
$("#main").addEventListener("click",event=>{const a=event.target.closest('a[href^="#"]');if(a){event.preventDefault();navigate(a.hash.slice(1));}});
$("#refresh").addEventListener("click",async()=>{if(S.dirty&&!confirm("刷新会丢弃未保存修改，继续吗？"))return;try{S.dirty=false;await reload();toast("已刷新本地数据");}catch(e){toast(e.message,true);}});
window.addEventListener("beforeunload",event=>{if(S.dirty){event.preventDefault();event.returnValue="";}});
reload().catch(error=>{$("#main").innerHTML=`<div class="empty"><h2>无法加载工作区</h2><p>${esc(error.message)}</p><p>请确认本地服务仍在运行，然后刷新页面。</p></div>`;});

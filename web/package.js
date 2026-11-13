"use strict";
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const md = window.markdownit({html:false, linkify:false});
md.renderer.rules.image = (tokens,index)=>`<span class="muted">[图片：${esc(tokens[index].content)}]</span>`;
const S = {sets:[],token:"",id:"default",node:"chapter-01",description:null,file:null,dirty:false,busy:false,serial:0};

async function api(path, data) {
  const response = await fetch(path,data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-BP-Token":S.token},body:JSON.stringify(data)});
  const result = await response.json();
  if(!response.ok)throw new Error(result.error||"操作失败，请重试。");
  return result;
}
function toast(text,error=false) {
  $("#toast").textContent=text;$("#toast").className=error?"visible error":"visible";
  clearTimeout(S.toastTimer);S.toastTimer=setTimeout(()=>$("#toast").className="",error?8000:3500);
}
function nodes(description=S.description) {
  const flatten = entries=>entries.flatMap(node=>[node,...flatten(node.children||[])]);
  return [...flatten(description.chapters),{id:"notes",title:"版本说明",path:description.notes},
    ...description.files.map((path,index)=>({id:`file-${index}`,title:path,path}))];
}
function route() {
  const [id="default",node="chapter-01"]=location.hash.slice(1).split("/");
  return {id:id||"default",node:node||"chapter-01"};
}
function leave() {return !S.dirty||confirm("有未保存的正文，确定离开吗？");}
function preview(body,path) {
  if(path.endsWith(".json"))return `<pre><code>${esc(body)}</code></pre>`;
  const text=body.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/,"");
  return md.render(text.replace(/^# [^\n]+\r?\n(?:\r?\n)?/,""));
}
function renderNavigation() {
  const item = node=>`<a href="#${S.id}/${node.id}" ${S.node===node.id?'class="active" aria-current="page"':""}>${esc(node.title)}</a>`;
  $("#navigation").innerHTML=S.description.chapters.map(chapter=>chapter.children.length?
    `<details class="chapter" ${chapter.id===S.node||chapter.children.some(n=>n.id===S.node)?"open":""}><summary>${item(chapter)}</summary><div class="children">${chapter.children.map(item).join("")}</div></details>`:
    `<div class="chapter single">${item(chapter)}</div>`).join("")+
    `<a class="notes-nav ${S.node==="notes"?"active":""}" href="#${S.id}/notes">版本说明 <span>↗</span></a><details class="file-list"><summary>全部文件 · ${S.description.files.length}</summary>${S.description.files.map((path,index)=>item({id:`file-${index}`,title:path})).join("")}</details>`;
  $("#notes-link").href=`#${S.id}/notes`;
}
function renderReading() {
  const node=nodes().find(n=>n.id===S.node), file=S.file;
  const copyButton=file.path.startsWith(".codex-bp/prompts/")?'<button id="copy-prompt" class="subtle">复制 Prompt</button>':"";
  $("#main").innerHTML=`<div class="page-meta"><span>${esc(S.description.title)}</span><span>／</span><span>${file.path===S.description.notes?"版本说明":"规范文件"}</span></div><div class="page-heading"><h1>${esc(node?.title||file.path)}</h1><div class="actions">${copyButton}${file.editable?'<button id="edit-file" class="subtle">编辑正文</button>':'<span class="readonly-label">只读</span>'}</div></div><div class="document-status"><span class="dot"></span>${S.description.readonly?"默认规范保持只读，需要修改时新建一套。":"自定义副本 · 修改后保存到本机，可下载整套文件。"}<a href="#${S.id}/notes">查看版本说明 →</a></div><article class="document markdown">${preview(file.body,file.path)}</article><details class="source-path"><summary>文件位置</summary><code>${esc(file.path)}</code></details>`;
}
function renderEditor() {
  $("#main").innerHTML=`<div class="page-meta">编辑自定义规范</div><div class="page-heading"><h1>${esc(nodes().find(n=>n.id===S.node)?.title||S.file.path)}</h1><div class="actions"><button id="cancel-edit">返回阅读</button><button id="save-file" class="primary">保存正文</button></div></div><p class="muted">${esc(S.file.path)} · 保存修改当前副本，默认原件保持不变。</p><p id="editor-error" class="error" role="alert"></p><div class="editor-layout"><section><label for="body-editor">正文</label><textarea id="body-editor" spellcheck="false" aria-label="规范正文"></textarea></section><section class="editor-preview"><div class="preview-label">预览</div><div class="markdown" id="body-preview"></div></section></div>`;
  $("#body-editor").value=S.file.body;$("#body-preview").innerHTML=preview(S.file.body,S.file.path);
  $("#body-editor").focus();
}
async function openCurrent() {
  const serial=++S.serial, requested=route();
  const description=await api(`/api/sets/${requested.id}`);
  if(serial!==S.serial)return;
  const entries=nodes(description), node=entries.find(n=>n.id===requested.node)||entries[0];
  const file=await api(`/api/sets/${requested.id}/file?path=${encodeURIComponent(node.path)}`);
  if(serial!==S.serial)return;
  S.id=requested.id;S.node=node.id;S.description=description;S.file=file;S.dirty=false;
  $("#set-picker").value=S.id;$("#set-badge").textContent=description.readonly?"只读默认":"自定义";
  $("#export-set").href=`/api/sets/${S.id}/export`;$("#export-set").download=`codex-${S.id==="default"?"default-1.0":S.id.slice(0,8)}.zip`;
  renderNavigation();renderReading();
  $(".sidebar").classList.remove("expanded");$("#menu-toggle").setAttribute("aria-expanded","false");$("#menu-toggle").textContent="展开目录";
  window.scrollTo(0,0);
}
async function refreshList() {
  const state=await api("/api/sets");S.sets=state.sets;S.token=state.token;
  $("#set-picker").innerHTML=state.sets.map(set=>`<option value="${set.id}">${esc(set.title)}</option>`).join("");
}
document.addEventListener("click",async event=>{
  const anchor=event.target.closest('a[href^="#"]');
  if(anchor){if(S.busy||!leave()){event.preventDefault();return;}S.dirty=false;if(anchor.hash===location.hash&&S.file)renderReading();}
  if(event.target.closest("#export-set")&&S.dirty){event.preventDefault();toast("先保存正文，再导出整套文件。",true);return;}
  try {
    if(event.target.closest("#create-set")) {
      if(!leave())return;
      $("#set-title").value=`${S.description.title} · 自定义`;$("#create-error").textContent="";
      $("#create-dialog").showModal();$("#set-title").focus();$("#set-title").select();
    }
    if(event.target.closest("#close-dialog,#cancel-create"))$("#create-dialog").close();
    if(event.target.closest("#edit-file")&&S.file.editable)renderEditor();
    if(event.target.closest("#copy-prompt")){await navigator.clipboard.writeText(S.file.body);toast("Prompt 已复制，请按实际任务填写输入。");}
    if(event.target.closest("#cancel-edit")&&leave()){S.dirty=false;renderReading();}
    if(event.target.closest("#save-file")&&!S.busy) {
      S.busy=true;$("#save-file").disabled=true;
      try {
        S.file=await api(`/api/sets/${S.id}/file`,{path:S.file.path,body:$("#body-editor").value,etag:S.file.etag});
        S.dirty=false;renderReading();toast("正文已保存。");
      }catch(error){$("#editor-error").textContent=error.message;$("#save-file").disabled=false;}
      finally{S.busy=false;}
    }
    if(event.target.closest("#menu-toggle")) {
      const open=$(".sidebar").classList.toggle("expanded");$("#menu-toggle").setAttribute("aria-expanded",String(open));$("#menu-toggle").textContent=open?"收起目录":"展开目录";
    }
  }catch(error){toast(error.message,true);}
});
$("#create-form").addEventListener("submit",async event=>{
  event.preventDefault();if(S.busy)return;S.busy=true;
  const button=event.target.querySelector('[type="submit"]');button.disabled=true;
  try {
    const created=await api("/api/sets",{source:S.id,title:$("#set-title").value});
    S.dirty=false;$("#create-dialog").close();await refreshList();location.hash=`${created.id}/${S.node}`;
    toast("整套副本已创建，可以编辑保存。");
  }catch(error){$("#create-error").textContent=error.message;}
  finally{S.busy=false;button.disabled=false;}
});
$("#set-picker").addEventListener("change",event=>{
  if(S.busy||!leave()){event.target.value=S.id;return;}S.dirty=false;location.hash=`${event.target.value}/${S.node}`;
});
document.addEventListener("input",event=>{
  if(event.target.id==="body-editor"){S.dirty=true;$("#body-preview").innerHTML=preview(event.target.value,S.file.path);}
});
window.addEventListener("hashchange",()=>{
  if(!leave()){history.replaceState(null,"",`#${S.id}/${S.node}`);return;}
  S.dirty=false;openCurrent().catch(error=>toast(error.message,true));
});
window.addEventListener("beforeunload",event=>{if(S.dirty){event.preventDefault();event.returnValue="";}});
(async()=>{try{await refreshList();await openCurrent();}catch(error){$("#main").innerHTML=`<div class="error" role="alert">${esc(error.message)}</div>`;}})();

// One Notes document browser: Letters, Mail, Tasks and workspace readers.
import {escape, lifecycle, localURL, viewState, fa} from './content-core.js';
import {sourceChange} from './source-changes.js';
let editorRuntime, markdownRuntime;
const loadEditor = () => editorRuntime ||= import('/static/vendor/code-editor.js').catch(error => { editorRuntime = null; throw error; });
const loadMarkdown = () => markdownRuntime ||= import('/static/vendor/notes-markdown/markdown-renderer.js').catch(error => { markdownRuntime = null; throw error; });

// Center the passage, but never scroll its first visual line above the viewport.
export function centerEditorRange(view,from,to,valid=()=>true){
  return new Promise(resolve=>{
    function measure(remaining){
      if(!valid()){resolve(false);return;}
      view.requestMeasure({
        read(){
          const scroll=view.scrollDOM,box=scroll.getBoundingClientRect(),height=scroll.clientHeight;
          if(!height)return null;
          const start=view.coordsAtPos(from,1),end=view.coordsAtPos(Math.max(from,to-1),1);
          const top=start?.top??view.documentTop+view.lineBlockAt(from).top;
          const bottom=end?.bottom??view.documentTop+view.lineBlockAt(Math.max(from,to-1)).bottom;
          const viewportTop=box.top+scroll.clientTop,margin=Math.min(16,height/4);
          const centered=(top+bottom-height)/2-viewportTop;
          const keepStart=top-viewportTop-margin;
          return Math.max(0,Math.min(scroll.scrollHeight-height,scroll.scrollTop+Math.min(centered,keepStart)));
        },
        write(top){
          if(!valid()){resolve(false);return;}
          if(top===null){resolve(false);return;}
          view.scrollDOM.scrollTop=top;
          // Recheck once after CodeMirror renders the newly visible wrapped lines.
          if(remaining)measure(remaining-1);else resolve(true);
        },
      });
    }
    // Materialize the start before measuring: an offscreen cursor can otherwise
    // have coordinates in a virtualized gap, especially after jumping upward.
    view.dispatch({effects:view.constructor.scrollIntoView(from,{y:'start',yMargin:16})});
    requestAnimationFrame(()=>measure(1));
  });
}

function keyValues(entries, render, array = false) {
  return `<table class="key-values"><tbody>${entries.map(([key,value]) => `<tr><th scope="row">${escape(array ? `[${key}]` : key)}</th><td>${render(value)}</td></tr>`).join('')}</tbody></table>`;
}
// JSON branches are materialized only when opened; indentation never accumulates.
function jsonRows(value, depth, branches) {
  const entries = Object.entries(value);
  if (!entries.length) return `<code>${Array.isArray(value) ? '[]' : '{}'}</code>`;
  return entries.map(([key, child]) => {
    const label = escape(Array.isArray(value) ? `[${key}]` : key);
    const level = Math.min(depth, 4);
    if (child !== null && typeof child === 'object') {
      const count = Object.keys(child).length;
      const id = branches.size;
      branches.set(String(id), {value:child, depth:depth + 1});
      return `<details class="json-branch" data-json-branch="${id}"><summary class="json-level-${level}"><span class="json-key">${label}</span><span class="json-count">${count} ${Array.isArray(child) ? (count === 1 ? 'item' : 'items') : (count === 1 ? 'field' : 'fields')}</span></summary><div class="json-children"></div></details>`;
    }
    const text = typeof child === 'string' ? child || '""' : String(child);
    return `<div class="json-field json-level-${level}"><div class="json-key">${label}</div><div class="json-${typeof child === 'string' ? 'string' : 'literal'}">${escape(text)}</div></div>`;
  }).join('');
}
export function jsonPreview(value, branches = new Map()) {
  if (value === null || typeof value !== 'object') return `<div class="json-tree"><span class="json-string">${escape(typeof value === 'string' ? value : String(value))}</span></div>`;
  return `<div class="json-tree">${jsonRows(value, 0, branches)}</div>`;
}
function mountJSON(canvas, value, signal) {
  const branches = new Map();
  canvas.innerHTML = jsonPreview(value, branches);
  // toggle does not bubble, but capture also works inside Letters' ShadowRoot.
  canvas.addEventListener('toggle', event => {
    const details = event.target;
    if (!details.matches?.('details[data-json-branch]') || !details.open || details.dataset.jsonLoaded) return;
    const branch = branches.get(details.dataset.jsonBranch);
    if (!branch) return;
    details.querySelector(':scope > .json-children').innerHTML = jsonRows(branch.value, branch.depth, branches);
    details.dataset.jsonLoaded = 'true';
  }, {capture:true, signal});
}
function frontmatter(source) {
  const match = source.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/);
  if (!match) return {body:source, metadata:''};
  const entries = match[1].split(/\r?\n/).flatMap(line => { const field = line.match(/^([A-Za-z0-9_-]+)\s*:\s*(.*)$/); return field ? [[field[1].replace(/[_-]/g,' '),field[2]]] : []; });
  return {body:source.slice(match[0].length), metadata:keyValues(entries, escape)};
}
export async function markdownPreview(source, {resolveResource, emoji = false, html: allowHTML = true, mentions = null, sourceMap = false} = {}) {
  const {body, metadata} = frontmatter(source);
  const html = await (await loadMarkdown()).renderMarkdown(body, '', {emoji, html:allowHTML, mentions, sourceMap});
  const template = document.createElement('template'); template.innerHTML = metadata + `<article class="doc-prose">${html}</article>`;
  // The renderer sanitizes HTML. Notes additionally confines local resources and blocks remote images.
  for (const link of template.content.querySelectorAll('a[href]')) {
    const href = link.getAttribute('href');
    if (href.startsWith('#')) continue;
    if (/^(https?:|mailto:)/i.test(href)) { link.target = '_blank'; link.rel = 'noopener noreferrer'; continue; }
    const resolved = resolveResource?.(href, false);
    if (resolved) link.href = localURL(resolved); else link.removeAttribute('href');
  }
  for (const image of template.content.querySelectorAll('img')) {
    const resolved = resolveResource?.(image.getAttribute('src'), true);
    if (resolved) image.src = localURL(resolved);
    else { const label = document.createElement('span'); label.className = 'notes-image-note'; label.textContent = image.alt ? `[Image: ${image.alt}]` : '[Image]'; image.replaceWith(label); }
  }
  // No arbitrary inline CSS from file contents. KaTeX layout uses a small numeric allowlist.
  for (const element of template.content.querySelectorAll('[style]')) {
    const style = element.getAttribute('style'); element.removeAttribute('style');
    if (element.closest('.katex')) for (const declaration of style.split(';')) {
      const [name, value] = declaration.split(':').map(part => part.trim());
      if (/^(height|width|top|left|vertical-align|margin-(left|right|top|bottom)|padding-(left|right)|border-(bottom|top)-width|font-size|position)$/.test(name) && /^(?:-?[\d.]+(?:em|ex|px|%)|relative|absolute)$/.test(value)) element.style.setProperty(name, value);
    }
  }
  return template.content;
}

export function mountContent(host, {source='', format='markdown', extension='', readOnly=true, sourceMode=false, sourceOnly=false, showModeToggle=true, sourceTitle='', sourceLabel='Show source', stateKey='', ariaLabel='Source editor', saveLabel='Save changes', dirty=false, className='', onInput=()=>{}, onSave=null, onReload=null, onModeChange=()=>{}, sourceMap=false, onRendered=()=>{}, onNavigate=null, presentation=null, resolveResource=null,recoveryContext=null} = {}) {
  if (!['markdown','json','text'].includes(format)) throw new Error('Unsupported content format.');
  let value = source, baseline = source, mode = sourceOnly ? true : presentation?.getMode?.() ?? viewState(stateKey).mode ?? sourceMode, editor = null, editorState = null, disposed = false, generation = 0, ready, saving = false, isDirty = dirty, readingPosition = null;
  const positions = {}, abort = new AbortController(),recovery=host.ownerDocument.defaultView?.DraftRecovery,owner=readOnly?null:recovery?.editors,recoveryKey='content:'+(stateKey||recovery?.editorKey(host,ariaLabel));
  let recoveryHandle=null,recoveryConflict=false;
  const resumed=(owner?.resume?owner.resume(recoveryKey):owner?.read(recoveryKey));
  if(resumed?.kind==='content'&&resumed.version===1&&(resumed.baseline===source||resumed.value===source||resumed.dirty&&recoveryContext)){value=resumed.value;baseline=resumed.dirty?resumed.baseline:source;mode=sourceOnly||resumed.mode;isDirty=value!==baseline;if(resumed.dirty&&recoveryContext)recoveryContext.restore(resumed.context);if(isDirty)onInput(value);}
  else if(resumed?.dirty){value=resumed.value;baseline=resumed.baseline;mode=sourceOnly||resumed.mode;isDirty=true;recoveryConflict=true;}
  let notice={message:dirty?'Unsaved changes':'',error:false,action:null},resolving=false;
  const destroy = lifecycle(host, () => { disposed = true; generation++; abort.abort(); recoveryHandle?.dispose(); readingPosition?.destroy(); editor?.destroy(); editorState = null; });
  const root = document.createElement('section'); root.className = 'content-browser'; if (className) root.classList.add(...className.split(/\s+/).filter(Boolean)); host.replaceChildren(root);
  function paintStatus(){
    const output=root.querySelector('[data-content-status]'),action=notice.action;
    if(output){output.textContent=notice.message;output.classList.toggle('has-error',notice.error);output.classList.toggle('has-action',!!action);output.setAttribute('role',action?'button':'status');output.title=action?.label||'';output.onclick=action?()=>resolve(action):null;output.onkeydown=action?event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();void resolve(action);}}:null;if(action){output.tabIndex=0;output.setAttribute('aria-disabled',String(saving||resolving));}else{output.removeAttribute('tabindex');output.removeAttribute('aria-disabled');}}
    const save=root.querySelector('[data-save]');if(save)save.disabled=saving||resolving||!isDirty;
    const reload=root.querySelector('[data-reload]');if(reload)reload.disabled=saving||resolving;
  }
  function status(message,error=false,action=null){notice={message,error,action};paintStatus();}
  async function resolve(action){
    if(saving||resolving||disposed)return;
    resolving=true;status('Merging latest file…');
    try{const result=await action.run();if(notice.message==='Merging latest file…')status(result===false?'Refresh deferred. Try again.':isDirty?'Unsaved changes':'File is up to date',result===false,result===false?action:null);}
    catch(error){status(error.message,true,action);}
    finally{resolving=false;paintStatus();}
  }
  async function save() {
    if (!onSave || readOnly || saving || resolving || !isDirty) return;
    if(recoveryConflict){status('The source changed while this draft was closed. Its recovery copy is retained; review the original before saving.',true);return;}
    const snapshot = value; saving = true; status('Saving…');
    try { if (format === 'json') JSON.parse(snapshot); const result = await onSave(snapshot); if (result === false) throw new Error('Could not save.'); baseline = typeof result?.savedSource === 'string' ? result.savedSource : snapshot; isDirty = value !== baseline; status(isDirty ? 'Unsaved changes' : 'Saved'); }
    catch (error) { status(error.message,true,error.recovery); }
    finally { saving = false; recoveryHandle?.touch();paintStatus(); }
  }
  async function render() {
    const current = ++generation;
    readingPosition?.destroy(); readingPosition = null;
    const old = editor?.scrollDOM || root.querySelector('.content-canvas');
    if (old) positions[mode ? 'preview' : 'source'] = {top:old.scrollTop,left:old.scrollLeft};
    if (editor) { editorState = editor.state; editor.destroy(); editor = null; }
    root.classList.toggle('is-source',mode);
    root.innerHTML = `<div class="view-toolbar">${!sourceOnly ? `<span class="view-format icon-caption" title="${escape(format === 'text' ? extension.toUpperCase() || 'Text' : format === 'markdown' ? 'Markdown' : 'JSON')}${readOnly ? ' · Read only' : ''}" aria-label="${escape(format)}${readOnly ? ' · Read only' : ''}">${fa(format === 'text' ? 'code' : format)}${readOnly ? fa('lock-keyhole') : ''}</span>` : ''}<span data-content-status role="status" aria-live="polite"></span>${mode && onSave && !readOnly ? `<button type="button" data-save aria-label="${escape(saveLabel)}" title="${escape(saveLabel)}" ${saving || !isDirty ? 'disabled' : ''}>${fa('save')}</button>` : ''}${showModeToggle ? `<button type="button" data-mode aria-label="${mode ? 'Show preview' : escape(sourceLabel)}" title="${mode ? 'Show preview' : escape(sourceLabel)}">${fa(mode ? 'preview' : 'code')}</button>` : ''}</div><div class="content-canvas" tabindex="0" aria-label="${mode ? escape(ariaLabel) : 'Document preview'}"></div>`;
    if(sourceOnly){
      root.querySelector('[data-mode]').remove();
      const title=document.createElement('span');title.className='source-title';title.textContent=sourceTitle;title.title=sourceTitle;root.querySelector('.view-toolbar').prepend(title);
    }else root.querySelector('[data-mode]')?.addEventListener('click', () => { mode = !mode; recoveryHandle?.touch(); viewState(stateKey,{mode}); onModeChange(mode); presentation?.setMode?.(mode); ready = render(); });
    root.querySelector('[data-save]')?.addEventListener('click',save);
    if(onReload){const reload=document.createElement('button');reload.type='button';reload.dataset.reload='';reload.title='Reload latest file';reload.setAttribute('aria-label','Reload latest file');reload.innerHTML=fa('arrows-rotate');reload.onclick=()=>resolve({label:'Merge latest file',run:onReload});root.querySelector('.view-toolbar').insertBefore(reload,root.querySelector('[data-save]')||root.querySelector('[data-mode]'));}
    const canvas = root.querySelector('.content-canvas');
    canvas.textContent = mode ? 'Loading editor…' : 'Loading preview…';
    canvas.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target.closest('a[href]');
      if (link && onNavigate?.(new URL(link.href, location.href), event) === true) { event.preventDefault(); event.stopPropagation(); }
    });
    if (!mode) canvas.addEventListener('keydown', event => {
      if (event.defaultPrevented || event.isComposing || event.altKey || !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'a') return;
      const selection = root.getRootNode().getSelection?.() || window.getSelection();
      if (!selection) return;
      const range = document.createRange(); range.selectNodeContents(canvas); selection.removeAllRanges(); selection.addRange(range);
      event.preventDefault(); event.stopPropagation();
    });
    readingPosition = presentation?.mountPosition?.(root, mode, () => editor?.scrollDOM || canvas) || null;
    const positionTracker = readingPosition;
    paintStatus();
    const valid = () => !disposed && generation === current && host.isConnected;
    try {
      if (mode) {
        const runtime = await loadEditor(); if (!valid()) return;
        canvas.replaceChildren();
        const view = await runtime.mountCodeEditor(canvas,value,extension || (format === 'markdown' ? 'md' : format === 'json' ? 'json' : 'txt'), next => { value = next; recoveryHandle?.touch(); const dirty = onInput(value); isDirty = typeof dirty === 'boolean' ? dirty : value !== baseline; if(notice.action)paintStatus();else status(isDirty ? 'Unsaved changes' : ''); }, undefined, {state:editorState,readOnly,ariaLabel,recoveryKey:stateKey||undefined,getBaseline:()=>baseline,onSave:onSave ? save : null,cspNonce:document.querySelector('meta[name="notes-style-nonce"]')?.content || ''});
        if (!valid()) { view.destroy(); return; } editor = view; editorState = null;
      } else if (format === 'markdown') { const fragment = await markdownPreview(value,{resolveResource,sourceMap}); if (!valid()) return; canvas.replaceChildren(fragment); }
      else if (format === 'json') mountJSON(canvas, JSON.parse(value), abort.signal);
      else { const text = document.createElement('pre'); text.className = 'text-preview'; text.textContent = value; canvas.replaceChildren(text); }
      if (!valid()) return;
      const scroll = editor?.scrollDOM || canvas, position = positions[mode ? 'source' : 'preview'];
      if (position) { scroll.scrollTop = position.top; scroll.scrollLeft = position.left; }
      paintStatus();
      if(!mode)onRendered(canvas,value);
      if (readingPosition === positionTracker) await positionTracker?.restore();
    } catch (error) { if (valid()) { canvas.textContent = error.message; status('Preview unavailable',true); } }
  }
  if(owner)recoveryHandle=owner.attach(recoveryKey,{owner:'Document editor',root:host,prepare:()=>!saving&&!resolving,capture:()=>({kind:'content',version:1,value,baseline,mode,dirty:isDirty,context:recoveryContext?.capture()})});
  ready = render();
  return {recoverySafe:()=>!!recoveryHandle?.safe()&&(!editor||!!editor.notesRecovery?.safe()),async updateSource(next,{saved=baseline,expected=value}={}){await ready;if(disposed||value!==expected)return false;const scroll=editor?.scrollDOM,top=scroll?.scrollTop,left=scroll?.scrollLeft,change=sourceChange(value,next),changed=change.from!==change.to||change.insert;baseline=saved;value=next;recoveryHandle?.touch();isDirty=value!==baseline;if(editor&&changed)editor.dispatch({changes:change});else{onInput(value);if(changed){editorState=null;ready=render();await ready;}}status(isDirty?'Unsaved changes':'Latest file loaded');if(scroll){scroll.scrollTop=top;scroll.scrollLeft=left;}return true;},setStatus:status,getSelection(){if(!editor)return null;const range=editor.state.selection.main,line=editor.state.doc.lineAt(range.head);return {from:range.from,to:range.to,head:range.head,line:line.number,column:range.head-line.from+1,screenY:editor.coordsAtPos(range.head)?.top};},
    async revealRange({from=0,to=from,line}={}){await ready;if(!editor||disposed)return false;if(line){const row=editor.state.doc.line(Math.max(1,Math.min(editor.state.doc.lines,line)));from=row.from;to=row.to;}from=Math.max(0,Math.min(value.length,from));to=Math.max(from,Math.min(value.length,to));const view=editor;view.dispatch({selection:{anchor:from,head:to}});view.focus();return centerEditorRange(view,from,to,()=>!disposed&&editor===view&&view.state.selection.main.from===from&&view.state.selection.main.to===to);},getSource:()=>value, getSourceMode:()=>mode, get ready(){return ready;}, save, destroy};
}

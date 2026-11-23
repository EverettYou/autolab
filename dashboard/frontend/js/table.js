'use strict';
// One keyboard navigator for Notes tables and selectable lists. Owners keep
// selection behavior; arrow navigation invokes the same explicit row/entry action.
(function(global){
 const bindings=new WeakMap(),memories=new Map();
 const editors='input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="combobox"],[role="menu"],[role="listbox"],[role="slider"],[role="spinbutton"],[role="tree"],[aria-haspopup],.app-select-trigger,.settings-more-menu,.cm-editor,.monaco-editor';
 function mount(host,options={}){
  if(!host?.querySelectorAll||!host.ownerDocument)return null;
  const existing=bindings.get(host);if(existing){existing.options=options;existing.sync();return existing;}
  const doc=host.ownerDocument,root=host.getRootNode();
  const previous=options.id&&memories.get(options.id);
  let activeKey=previous?.key??null,focusedRow=null,observer,restorePending=!!(previous?.focused&&!previous.host.isConnected);
  const originals=new WeakMap();let managed=new Set();
  const binding={options,sync,destroy};bindings.set(host,binding);
  function rows(){
   const source=binding.options.items||'tbody > tr';
   return [...(typeof source==='function'?source():host.querySelectorAll(source))].filter(row=>
    host.contains(row)&&!row.closest('[hidden],[inert],[aria-hidden="true"]')&&!row.matches(':disabled,[aria-disabled="true"]')&&
    (host.tagName!=='TABLE'||row.closest('table')===host));
  }
  function key(row,index){return String(binding.options.key?.(row)??(row.id||index));}
  function target(row){return binding.options.focus?.(row)||row;}
  function selected(row){return binding.options.selected?.(row)??row.matches('.selected,.sel,[aria-selected="true"],[aria-current="page"]');}
  function currentFocus(){return root.nodeType===11?root.activeElement:doc.activeElement;}
  function idle(){const active=currentFocus();return (!active||active===doc.body||active===host)&&(root.nodeType!==11||doc.activeElement===root.host||doc.activeElement===doc.body);}
  function remember(focused){if(binding.options.id)memories.set(binding.options.id,{host,key:activeKey,focused});}
  function release(node){const original=originals.get(node);if(!original)return;if(original.tab===null)node.removeAttribute('tabindex');else node.setAttribute('tabindex',original.tab);if(!original.styled)node.classList.remove('list-focus');originals.delete(node);}
  function focus(row){
   const list=rows();activeKey=key(row,list.indexOf(row));focusedRow=row;
   sync();target(row).focus({preventScroll:true});
   row.scrollIntoView?.({block:'nearest',inline:'nearest'});
  }
  function sync(){
   const list=rows(),active=currentFocus(),within=list.find(row=>row===active||row.contains(active));
   if(within){activeKey=key(within,list.indexOf(within));focusedRow=within;remember(true);}
   const current=within||list.find((row,index)=>key(row,index)===activeKey)||list.find(selected)||list[0];
   const next=new Set();
   for(const row of list){const node=target(row);next.add(node);if(!originals.has(node))originals.set(node,{tab:node.getAttribute('tabindex'),styled:node.classList.contains('list-focus')});node.classList.add('list-focus');const value=row===current?0:-1;if(!node.hasAttribute('tabindex')||node.tabIndex!==value)node.tabIndex=value;}
   for(const node of managed)if(!next.has(node))release(node);managed=next;
   // Letters and paginated lists replace their rows during selection/refresh.
   // Restore only lost list focus, never focus an editor, menu or other pane.
   const lost=restorePending||focusedRow&&!focusedRow.isConnected;
   if(lost){
    const replacement=list.find((row,index)=>key(row,index)===activeKey);
    focusedRow=null;restorePending=false;
    if(replacement&&idle()){focusedRow=replacement;target(replacement).focus({preventScroll:true});}
   }
  }
  function onClick(event){
   const origin=event.composedPath?.()[0]||event.target;
   if(origin.closest?.(editors+',button,a'))return;
   const row=rows().find(row=>row===origin||row.contains(origin));if(row)focus(row);
  }
  function onFocus(event){const list=rows(),row=list.find(row=>row===event.target||row.contains(event.target));if(row){activeKey=key(row,list.indexOf(row));focusedRow=row;sync();}}
  function onBlur(event){if(event.relatedTarget&&!host.contains(event.relatedTarget)){focusedRow=null;remember(false);}}
  function onKey(event){
   if(event.defaultPrevented||event.isComposing||event.ctrlKey||event.metaKey||event.altKey||event.shiftKey||!['ArrowUp','ArrowDown'].includes(event.key))return;
   const origin=event.composedPath?.()[0]||event.target;
   if(origin.closest?.(editors)||origin.closest?.('[data-table-navigation="off"]'))return;
   const list=rows();if(!list.length)return;
   const row=list.find(row=>row===origin||row.contains(origin));
   if(!row&&origin!==host)return; // Header controls and unrelated panes keep native keys.
   const index=row?list.indexOf(row):list.findIndex(selected);
   const next=index<0?(event.key==='ArrowDown'?0:list.length-1):Math.max(0,Math.min(list.length-1,index+(event.key==='ArrowDown'?1:-1)));
   event.preventDefault();event.stopPropagation();
   const destination=list[next];focus(destination);
   if(destination!==row){if(binding.options.activate)binding.options.activate(destination);else target(destination).click();}
   sync();
  }
  function destroy(){observer?.disconnect();host.removeEventListener('click',onClick);host.removeEventListener('keydown',onKey);host.removeEventListener('focusin',onFocus);host.removeEventListener('focusout',onBlur);for(const node of managed)release(node);managed.clear();bindings.delete(host);if(memories.get(binding.options.id)?.host===host)memories.delete(binding.options.id);}
  host.addEventListener('click',onClick);host.addEventListener('keydown',onKey);host.addEventListener('focusin',onFocus);host.addEventListener('focusout',onBlur);
  const Observer=doc.defaultView?.MutationObserver;
  if(Observer){observer=new Observer(()=>{if(host.isConnected)sync();else observer.disconnect();});observer.observe(host,{childList:true,subtree:true});}
  sync();return binding;
 }
 global.ListNavigation={mount};
})(window);

'use strict';
// Shared table structure, geometry and input; callers own rows and business actions.
(()=>{
 const mounted=new WeakMap();
 let preferences=null;
 function configure({api,data,namespace,workspaces=[],browsing={}}){
  if(!data)return;
  if(preferences){preferences.observe(data);return;}
  preferences=window.TablePreferences.create({api,initial:data});
  window.PaneArrangement?.configure(preferences);
  void preferences.importMany({...window.TablePreferences.legacySettings(localStorage,namespace,workspaces,browsing),...preferences.legacy()});
 }
 function nextSort(state,key,initial=1){return {key,direction:state.key===key?-state.direction:initial};}
 function resize(handle,adapter){
  if(handle.dataset.tableResize)return;
  handle.dataset.tableResize='';handle.classList.add('data-table-resizer');
  let active=null;
  const finish=(event,cancel=false)=>{
   if(active!==event.pointerId)return;active=null;
   (cancel?adapter.cancel||adapter.finish:adapter.finish)?.(event);
   if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);
   document.documentElement.classList.remove('data-table-resizing');
  };
  handle.onpointerdown=event=>{
   if(event.button!==0)return;event.preventDefault();event.stopPropagation();
   active=event.pointerId;adapter.start?.(event);handle.setPointerCapture(event.pointerId);
   document.documentElement.classList.add('data-table-resizing');
  };
  handle.onpointermove=event=>{if(active===event.pointerId)adapter.move?.(event);};
  handle.onpointerup=event=>finish(event);handle.onpointercancel=event=>finish(event,true);
  handle.onlostpointercapture=event=>finish(event,true);
  handle.onkeydown=event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();event.stopPropagation();adapter.key?.(event);}};
 }
 // Allocate a shared full-width table while preserving stored proportions and
 // content minimums. All business tables use this same geometry, not CSS widths.
 function allocate(keys,values,minimums,available){
  const widths={},pending=new Set(keys);let remaining=Math.max(available,keys.reduce((n,k)=>n+minimums[k],0));
  while(pending.size){
   const total=[...pending].reduce((n,k)=>n+values[k],0),locked=[...pending].filter(key=>remaining*values[key]/total<minimums[key]);
   if(!locked.length){for(const key of pending)widths[key]=remaining*values[key]/total;break;}
   for(const key of locked){widths[key]=minimums[key];remaining-=widths[key];pending.delete(key);}
  }
  return widths;
 }
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 // Standard structural template; owners supply column identities and row content.
 function header(columns){return '<colgroup>'+columns.map(c=>`<col data-table-width="${escape(c.key||c.id)}">`).join('')+'</colgroup><thead><tr>'+columns.map(c=>`<th scope="col" data-table-column="${escape(c.key||c.id)}" data-table-label="${escape(c.label||c.name)}"><span class="data-table-heading"></span></th>`).join('')+'</tr></thead>';}
 function columnLayout(table,binding){
  let values={},widths={},keys=[],minimums={},drag=null,options=binding.adapter.layout||{},columns=[];
  let unsubscribe=null,subscribed='',notice=null,lastError='';
  function preferenceFeedback(){
   const error=preferences.error(options.id);
   if(error&&!notice){notice=document.createElement('caption');notice.className='data-table-save-status';notice.setAttribute('aria-live','polite');table.prepend(notice);}
   if(notice){notice.hidden=!error;if(error){const text=document.createElement('span');text.textContent=error;const retry=document.createElement('button');retry.type='button';retry.textContent='Retry saving settings';retry.onclick=()=>void preferences.retry(options.id);notice.replaceChildren(text,retry);}}
   if(error&&error!==lastError)table.dispatchEvent(new CustomEvent('data-table-save-error',{detail:new Error(error),bubbles:true}));lastError=error;
  }
  function preferenceChanged(){
   if(!table.isConnected){unsubscribe?.();return;}
   preferenceFeedback();sync();
  }
  const host=()=>options.host||table.parentElement;
  function paint(){
   if(!keys.length)return;
   widths=allocate(keys,values,minimums,host()?.clientWidth||table.clientWidth||keys.reduce((n,k)=>n+values[k],0));
   table.style.width=Object.values(widths).reduce((a,b)=>a+b,0)+'px';
   table.querySelectorAll('colgroup col').forEach((col,i)=>{if(keys[i])col.style.width=widths[keys[i]]+'px';});
   for(const col of columns){
    const handle=col.resizer,right=keys[keys.indexOf(col.key)+1];if(!handle||!right)continue;
    const max=Math.max(minimums[col.key],Math.min(Number(options.max)||2400,widths[col.key]+widths[right]-minimums[right]));
    handle.setAttribute('aria-valuemin',String(minimums[col.key]));handle.setAttribute('aria-valuemax',String(Math.round(max)));handle.setAttribute('aria-valuenow',String(Math.round(widths[col.key])));
   }
  }
  function sync(){
   options=binding.adapter.layout||{};columns=binding.adapter.columns();columns.forEach(c=>c.resizer=c.cell.querySelector('.data-table-resizer'));keys=columns.map(c=>c.key);
   if(drag)return;
   let stored={};try{stored=options.values?.()||(options.key?JSON.parse(localStorage.getItem(options.key)||(options.legacyKey?localStorage.getItem(options.legacyKey):null)||'{}'):values);}catch{}
   if(preferences&&options.id){
    if(subscribed!==options.id){unsubscribe?.();subscribed=options.id;unsubscribe=preferences.subscribe(options.id,preferenceChanged);preferenceFeedback();if(!preferences.has(options.id))void preferences.importMany({[options.id]:stored});}
    if(preferences.has(options.id))stored=preferences.values(options.id);
   }
   if(!stored||typeof stored!=='object'||Array.isArray(stored))stored={};
   const defaults=typeof options.defaults==='function'?options.defaults():options.defaults||{};
   const mins=typeof options.minimums==='function'?options.minimums():options.minimums||{};
   values={...stored};minimums={};for(const key of keys){values[key]=Number.isFinite(stored[key])&&stored[key]>0?stored[key]:Number(defaults[key])>0?Number(defaults[key]):160;minimums[key]=Math.max(40,Number(mins[key])||Number(options.min)||70);}
   if(options.contentMinimums!==false&&table.ownerDocument?.body){
    const doc=table.ownerDocument,probe=doc.createElement('span');
    probe.style.cssText='position:fixed;visibility:hidden;white-space:pre;pointer-events:none';doc.body.append(probe);
    const measure=(text,node)=>{probe.style.font=doc.defaultView.getComputedStyle(node).font;probe.textContent=text;return probe.getBoundingClientRect().width||text.length*7;};
    columns.forEach((column,index)=>{
     const label=column.label||column.cell.dataset.tableLabel||'';
     let required=measure(label,column.cell)+36;
     for(const row of table.querySelectorAll('tbody tr')){
      const cell=row.children[index];if(!cell)continue;
      // Inline badges have their own padding and gaps that word-based
      // measurement misses. Measure the rendered badge and retain the cell's
      // horizontal breathing room so its contents never get squeezed.
      const badge=cell.querySelector('.edencode-state,.type-badge');
      if(badge){
       const cellStyle=doc.defaultView.getComputedStyle(cell);
       required=Math.max(required,Math.max(badge.getBoundingClientRect().width,badge.scrollWidth)+(parseFloat(cellStyle.paddingLeft)||0)+(parseFloat(cellStyle.paddingRight)||0));
      }
      const words=(cell.textContent||'').trim().split(/\s+/);
      required=Math.max(required,...words.map(word=>Math.min(160,measure(word,cell))+20));
     }
     // Catalog values must fit even when current filters show no matching row.
     const extra=options.minimumLabels?.[column.key];
     if(extra?.labels?.length){
      const sample=doc.createElement('span');sample.className=extra.className||'';
      sample.setAttribute('aria-hidden','true');sample.style.cssText='position:absolute;visibility:hidden;white-space:nowrap;pointer-events:none;width:max-content;max-width:none';column.cell.append(sample);
      const style=doc.defaultView.getComputedStyle(sample),cellStyle=doc.defaultView.getComputedStyle(column.cell);
      const padding=(parseFloat(style.paddingLeft)||0)+(parseFloat(style.paddingRight)||0)+(parseFloat(style.borderLeftWidth)||0)+(parseFloat(style.borderRightWidth)||0);
      const room=(parseFloat(cellStyle.paddingLeft)||0)+(parseFloat(cellStyle.paddingRight)||0)||20;
      for(const text of extra.labels){sample.textContent=text;required=Math.max(required,Math.max(sample.getBoundingClientRect().width,sample.scrollWidth,measure(text,sample)+padding)+room);}
      sample.remove();
     }
     minimums[column.key]=Math.ceil(Math.max(40,required));
    });probe.remove();
   }
   let group=table.querySelector('colgroup');if(!group){group=document.createElement('colgroup');table.prepend(group);}
   if(group.children.length!==keys.length)group.replaceChildren(...keys.map(()=>document.createElement('col')));
   paint();
  }
  function commit(){
   try{const result=preferences&&options.id?preferences.save(options.id,values):options.persist?options.persist({...values}):options.key?localStorage.setItem(options.key,JSON.stringify(values)):null;Promise.resolve(result).catch(error=>table.dispatchEvent(new CustomEvent('data-table-save-error',{detail:error,bubbles:true})));}
   catch(error){table.dispatchEvent(new CustomEvent('data-table-save-error',{detail:error,bubbles:true}));}
  }
  function change(index,delta,initial){
   const left=keys[index],right=keys[index+1];if(!right)return;
   // Normalize visible weights to the displayed geometry before adjusting a pair.
   // Otherwise a minimum-clamped column can make unrelated columns move too.
   const totalPx=keys.reduce((n,k)=>n+initial.widths[k],0),total=keys.reduce((n,k)=>n+initial.values[k],0);
   for(const key of keys)values[key]=initial.widths[key]*total/totalPx;
   const pairPx=initial.widths[left]+initial.widths[right],pair=values[left]+values[right];
   const next=Math.max(minimums[left],Math.min(pairPx-minimums[right],Number(options.max)||2400,initial.widths[left]+delta));
   values[left]=pair*next/pairPx;values[right]=pair-values[left];paint();
  }
  function adapter(column){return {
   start:event=>{drag={index:keys.indexOf(column.key),x:event.clientX,values:{...values},widths:{...widths}};},
   move:event=>{if(drag)change(drag.index,event.clientX-drag.x,drag);},
   finish:()=>{if(drag){drag=null;commit();}},
   cancel:()=>{if(drag){values=drag.values;drag=null;paint();}},
   key:event=>{const index=keys.indexOf(column.key);change(index,(event.key==='ArrowRight'?1:-1)*(event.shiftKey?20:5),{values:{...values},widths:{...widths}});commit();}
  };}
  const observer=typeof ResizeObserver!=='undefined'?new ResizeObserver(()=>{if(!table.isConnected){observer.disconnect();return;}paint();}):null;
  observer?.observe(host());
  return {sync,paint,adapter,destroy(){observer?.disconnect();unsubscribe?.();}};
 }
 function mount(table,adapter={}){
  const columns=adapter.columns||(()=>[...table.querySelectorAll('thead th')].map((cell,i)=>({cell,key:cell.dataset.tableColumn||String(i),label:cell.dataset.tableLabel||cell.textContent.trim(),host:cell.querySelector('.data-table-heading')})));
  adapter={...adapter,columns};
  let binding=mounted.get(table);
  if(binding){binding.adapter=adapter;binding.sync();return binding;}
  table.classList.add('data-table');
  const overflowTitles=new WeakMap();
  function revealOverflow(event){
   const origin=event.target?.nodeType===3?event.target.parentElement:event.target;
   const cell=origin?.closest?.('td,th');
   if(!cell||cell.closest('table')!==table)return;
   for(const node of [cell,...cell.querySelectorAll('*')]){
    const managed=overflowTitles.get(node);
    if(managed!==undefined){
     if(node.getAttribute('title')===managed)node.removeAttribute('title');
     overflowTitles.delete(node);
    }
   }
   for(let node=origin;node&&cell.contains(node);node=node.parentElement){
    if(node.hasAttribute('title'))return;
    const style=table.ownerDocument.defaultView.getComputedStyle(node);
    const clipped=(node.scrollWidth>node.clientWidth+1||node.scrollHeight>node.clientHeight+1)&&
     (style.textOverflow==='ellipsis'||style.overflow==='hidden'||style.overflowX==='hidden'||style.overflowY==='hidden');
    if(clipped){
     const text=(node.innerText||node.textContent||'').trim();
     if(text){node.setAttribute('title',text);overflowTitles.set(node,text);}return;
    }
    if(node===cell)break;
   }
  }
  table.addEventListener('mouseover',revealOverflow);
  table.addEventListener('focusin',revealOverflow);

  binding={adapter,controls:new Map(),sync};mounted.set(table,binding);
  if(adapter.layout||!adapter.resize&&table.querySelector)binding.layout=columnLayout(table,binding);
  function sync(){
   const current=binding.adapter;
   for(const [cell] of binding.controls)if(!table.contains(cell))binding.controls.delete(cell);
   for(const column of current.columns()){
    const {cell,key,label}=column;
    if(current.sort&&current.sortable!==false){let control=binding.controls.get(cell);
    if(!control||!control.button.isConnected){
     const button=document.createElement('button');button.type='button';button.className='data-table-sort';button.dataset.tableSort=key;
     const text=document.createElement('span');text.className='data-table-label';
     const arrow=document.createElement('span');arrow.className='data-table-direction';arrow.setAttribute('aria-hidden','true');button.append(text,arrow);
     (column.host||cell).append(button);control={button,text,arrow};binding.controls.set(cell,control);
    }
    if(control.text.textContent!==label)control.text.textContent=label;
    const state=current.state?.(key)||{active:false,direction:1},direction=state.direction===-1?-1:1;
    const aria=state.active?(direction===1?'ascending':'descending'):'none';
    if(cell.getAttribute('aria-sort')!==aria)cell.setAttribute('aria-sort',aria);
    cell.scope='col';cell.dataset.tableColumn=key;
    const title='Sort by '+label+(state.active?(direction===1?', descending':', ascending'):'');
    if(control.button.title!==title)control.button.title=title;
    if(control.arrow.dataset.direction!==String(direction)){control.arrow.dataset.direction=String(direction);control.arrow.innerHTML=WorkbenchIcons.html(direction===1?'sortUp':'sortDown');}
    }else if(!cell.querySelector('.data-table-label')){const labelNode=document.createElement('span');labelNode.className='data-table-label';labelNode.textContent=label;(column.host||cell).append(labelNode);cell.dataset.tableColumn=key;}
    if(binding.layout){
     const all=current.columns(),index=all.findIndex(c=>c.key===key);
     if(index<all.length-1&&!column.resizer){let handle=cell.querySelector('.data-table-resizer');if(!handle){handle=document.createElement('span');cell.append(handle);}column.resizer=handle;}
     else if(index===all.length-1){(column.resizer||cell.querySelector('.data-table-resizer'))?.remove();column.resizer=null;}
     if(column.resizer){const h=column.resizer;h.tabIndex=0;h.setAttribute('role','separator');h.setAttribute('aria-orientation','vertical');h.setAttribute('aria-label','Resize '+label+' column');resize(h,binding.layout.adapter(column));}
    }else if(column.resizer&&!column.resizer.dataset.tableResize)resize(column.resizer,current.resize(column));
   }
   binding.layout?.sync();
   if(current.navigation===false){binding.navigation?.destroy();binding.navigation=null;}
   else binding.navigation=window.ListNavigation?.mount(table,{
    id:current.layout?.id||current.layout?.key,
    items:()=>[...table.querySelectorAll('tbody > tr')].filter(row=>row.querySelector('td')&&!row.querySelector('td[colspan]')),
    ...current.navigation
   });
  }
  table.addEventListener('click',event=>{
   const cell=event.target.closest('th[data-table-column]');if(!cell||!table.contains(cell)||event.target.closest('.data-table-resizer'))return;
   // Hidden native adapter controls must retain their own source handlers.
   if(event.target.closest('[data-table-native-control]'))return;
   if(event.target.closest('button,a,input,select')&&!event.target.closest('.data-table-sort'))return;
   if(!binding.adapter.sort||binding.adapter.sortable===false)return;
   event.preventDefault();event.stopImmediatePropagation();binding.adapter.sort(cell.dataset.tableColumn);binding.sync();
  },true);
  binding.sync();return binding;
 }
 // Compatibility entry point; resizing has one owner, including older callers.
 function adjustable(table,{key,columns,minimum=70}){
  return mount(table,{columns:()=>columns,layout:{key,min:minimum}});
 }
 function settings(id,seed){if(seed)void preferences?.importMany({[id]:seed});return {...seed,...preferences?.settings(id)};}
 function remember(id,patch){const work=preferences?.saveSettings(id,patch);return Promise.resolve(work).then(()=>{const error=preferences?.error(id);if(error)throw Error(error);});}
 window.DataTables={settings,remember,importSettings:(id,seed)=>preferences?.importMany({[id]:seed}),configure,mount,resize,adjustable,nextSort,header,allocate,relayout(table){mounted.get(table)?.layout?.sync();},catalogs:{tasks:[['title','Task'],['type','Type'],['due','Due'],['status','Status']]}};
})();

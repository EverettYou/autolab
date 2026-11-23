'use strict';
// Shared pointer/keyboard resizing. Widths are presentation preferences only.
(()=>{
 const bindings=new Map(),preferences=new Map();
 const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
 function drag(handle,{get,set,start=()=>{},finish=()=>{},axis='x'}){
  let active=null;
  const listeners=[];
  const on=(type,fn)=>{handle.addEventListener(type,fn);listeners.push(()=>handle.removeEventListener?.(type,fn));};
  const coordinate=e=>axis==='y'?e.clientY:e.clientX;
  const end=(event,cancel=false)=>{
   if(!active||event.pointerId!==active.id)return;
   const previous=active;active=null;
   if(cancel)set(previous.value);else set(previous.value+coordinate(event)-previous.start);
   document.documentElement.classList.remove('pane-dragging','pane-dragging-y');
   if(handle.hasPointerCapture(previous.id))handle.releasePointerCapture(previous.id);
   finish(!cancel);
  };
  on('pointerdown',event=>{
   if(event.button!==0||event.target.closest('button'))return;
   event.preventDefault();event.stopPropagation();
   active={id:event.pointerId,start:coordinate(event),value:get()};
   start();
   handle.setPointerCapture(event.pointerId);document.documentElement.classList.add('pane-dragging');if(axis==='y')document.documentElement.classList.add('pane-dragging-y');
  });
  on('pointermove',event=>{if(active&&event.pointerId===active.id)set(active.value+coordinate(event)-active.start);});
  on('pointerup',event=>end(event));
  on('pointercancel',event=>end(event,true));
  on('lostpointercapture',event=>end(event,true));
  on('keydown',event=>{
   const negative=axis==='y'?'ArrowUp':'ArrowLeft',positive=axis==='y'?'ArrowDown':'ArrowRight';
   if(event.target!==handle||![negative,positive,'Home','End'].includes(event.key))return;
   event.preventDefault();set(event.key==='Home'?-Infinity:event.key==='End'?Infinity:get()+(event.key===positive?1:-1)*(event.shiftKey?50:20));finish(true);
  });
  return ()=>{if(active)end({pointerId:active.id},true);listeners.forEach(remove=>remove());};
 }
 // A shared list/detail workspace, used in the document and in native ShadowRoots.
 // Callers own content and persistence; this controller owns all pane behavior.
 function workspace(root,{leading,trailing,handle,toggle,state={width:null,height:340,collapsed:false},label='list',enabled=()=>true,onChange=()=>{},breakpoint=578,proportional=false,collapsible=true,minLeading=240,minTrailing=332,minHeight=140,minDetailHeight=480,detailOnNarrow=false}={}){
  const doc=root.ownerDocument,view=doc.defaultView;
  const ownHandle=!handle;
  if(!handle){handle=doc.createElement('div');root.append(handle);}
  if(!toggle&&collapsible){toggle=doc.createElement('button');toggle.type='button';handle.append(toggle);}
  root.classList.add('list-detail');leading.classList.add('list-pane');trailing.classList.add('detail-pane');handle.classList.add('workspace-divider');toggle?.classList.add('pane-toggle');
  handle.tabIndex=0;handle.setAttribute('role',collapsible?'group':'separator');
  let vertical=false,active=null,destroyed=false;
  const listeners=[];
  const on=(node,type,fn)=>{node.addEventListener(type,fn);listeners.push(()=>node.removeEventListener(type,fn));};
  const cls=(name,value)=>{if(root.classList.contains(name)!==value)root.classList.toggle(name,value);};
  const attr=(node,key,value)=>{if(node.getAttribute(key)!==String(value))node.setAttribute(key,String(value));};
  const valid=(value,fallback)=>Number.isFinite(value)&&value>0?value:fallback;
  const minimum=()=>vertical?minHeight:minLeading;
  const maximum=()=>vertical?(collapsible?Infinity:Math.max(minHeight,root.clientHeight-minDetailHeight-1)):Math.max(0,root.clientWidth-minTrailing-(proportional?1:0));
  const size=()=>vertical?valid(state.height,collapsible?340:root.clientHeight*.55):proportional?root.clientWidth*valid(state.ratio,.6):valid(state.width,root.clientWidth*.48);
  function refresh(){
   if(destroyed)return;
   const nextVertical=root.clientWidth<breakpoint;
   // Switching orientation mid-gesture cancels the old axis rather than saving it.
   if(active&&nextVertical!==vertical)cancel();
   vertical=nextVertical;
   const visible=!!enabled();
   cls('notes-mobile-detail',detailOnNarrow&&vertical&&visible);
   cls('notes-panes-vertical',vertical);cls('list-collapsed',state.collapsed===true);cls('notes-no-detail',!visible);
   const width=proportional?clamp(root.clientWidth*valid(state.ratio,.6),minLeading,Math.max(minLeading,root.clientWidth-minTrailing-(proportional?1:0))):Math.min(valid(state.width,root.clientWidth*.48),Math.max(0,root.clientWidth-minTrailing-(proportional?1:0)));
   root.style.setProperty('--list-width',width+'px');
   root.style.setProperty('--list-height',(collapsible?valid(state.height,340):clamp(valid(state.height,root.clientHeight*.55),minHeight,Math.max(minHeight,root.clientHeight-minDetailHeight-1)))+'px');
   attr(handle,'aria-label','Resize '+label+(vertical?' height':' width'));
   if(!collapsible){attr(handle,'aria-orientation',vertical?'horizontal':'vertical');attr(handle,'aria-valuemin',minimum());attr(handle,'aria-valuemax',maximum());attr(handle,'aria-valuenow',Math.round(vertical?leading.getBoundingClientRect().height:width));return;}
   // A group keeps its nested button accessible; orientation is reflected by its label.
   attr(toggle,'aria-label',(state.collapsed?'Show ':'Hide ')+label);
   attr(toggle,'title',toggle.getAttribute('aria-label'));attr(toggle,'aria-expanded',!state.collapsed);
   const direction=state.collapsed?(vertical?'down':'next'):(vertical?'up':'previous');
   if(toggle.dataset.direction!==direction){toggle.dataset.direction=direction;toggle.innerHTML=view.WorkbenchIcons.html(direction);}
  }
  function save(){onChange({...state});}
  function restore(previous){Object.assign(state,previous);}
  function cancel(){
   if(!active)return;
   const previous=active;active=null;restore(previous.state);cls('workspace-dragging',false);
   if(handle.hasPointerCapture?.(previous.id))handle.releasePointerCapture(previous.id);
  }
  const coordinate=event=>vertical?event.clientY:event.clientX;
  function preview(event){
   const amount=coordinate(event)-active.start;
   if(Math.abs(amount)>3)active.moved=true;
   if(!active.moved)return;
   active.size=Math.max(collapsible?0:minimum(),Math.min(active.sizeAtStart+amount,maximum()));
   state.collapsed=false;state[vertical?'height':'width']=active.size;if(proportional&&!vertical)state.ratio=active.size/root.clientWidth;refresh();
  }
  if(toggle)on(toggle,'pointerdown',event=>event.stopPropagation());
  if(toggle)on(toggle,'click',event=>{event.preventDefault();event.stopPropagation();state.collapsed=!state.collapsed;refresh();save();});
  on(handle,'pointerdown',event=>{
   if(event.button!==0||event.target.closest('button')||!enabled())return;
   event.preventDefault();event.stopPropagation();
   const bounds=leading.getBoundingClientRect(),startSize=state.collapsed?0:vertical?bounds.height:bounds.width;
   active={id:event.pointerId,start:coordinate(event),sizeAtStart:startSize,size:startSize,state:{...state},moved:false};
   cls('workspace-dragging',true);handle.setPointerCapture?.(event.pointerId);
  });
  on(handle,'pointermove',event=>{if(active&&event.pointerId===active.id){event.preventDefault();preview(event);}});
  on(handle,'pointerup',event=>{
   if(!active||event.pointerId!==active.id)return;
   event.preventDefault();preview(event);const previous=active;active=null;
   if(previous.moved){if(previous.size<minimum()){restore(previous.state);state.collapsed=true;}}else restore(previous.state);
   cls('workspace-dragging',false);
   if(handle.hasPointerCapture?.(previous.id))handle.releasePointerCapture(previous.id);
   refresh();if(previous.moved)save();
  });
  const cancelled=event=>{if(active&&event.pointerId===active.id){cancel();refresh();}};
  on(handle,'pointercancel',cancelled);on(handle,'lostpointercapture',cancelled);
  on(handle,'keydown',event=>{
   if(event.target!==handle||!enabled())return;
   if(collapsible&&(event.key==='Enter'||event.key===' ')){event.preventDefault();toggle.click();return;}
   const negative=vertical?'ArrowUp':'ArrowLeft',positive=vertical?'ArrowDown':'ArrowRight';
   if(![negative,positive,'Home','End'].includes(event.key))return;
   event.preventDefault();
   if(event.key==='Home'&&collapsible)state.collapsed=true;
   else{
    const value=event.key==='Home'?minimum():event.key==='End'?(vertical?(collapsible?Math.max(340,root.clientHeight-160):maximum()):maximum()):Math.max(collapsible?0:minimum(),Math.min(size()+(event.key===positive?1:-1)*(event.shiftKey?50:24),maximum()));
    state.collapsed=collapsible&&value<minimum();if(!state.collapsed){state[vertical?'height':'width']=value;if(proportional&&!vertical)state.ratio=value/root.clientWidth;}
   }
   refresh();save();
  });
  const resize=new view.ResizeObserver(refresh);resize.observe(root);
  const changes=new view.MutationObserver(refresh);changes.observe(root,{attributes:true,attributeFilter:['class']});
  refresh();
  return {refresh,state,destroy(){cancel();destroyed=true;resize.disconnect();changes.disconnect();listeners.forEach(remove=>remove());if(ownHandle)handle.remove();}};
 }
 // Notes only needs SplitPanes.drag for the project tree / editor splitters.
 const specs=[];
 function mount(root,spec){
  const leading=root.querySelector(spec.leading);if(!leading)return;
  if(spec.workspace&&spec.key==='calendar'){
   // Keep one detail slot through side-by-side and stacked layouts, including
   // the fixed in-place editor which uses this slot's actual rectangle.
   const slot=document.createElement('div');slot.className='cal-detail-slot';root.append(slot);
   let state={ratio:null,height:null,collapsed:false};
   try{const saved=JSON.parse(localStorage.getItem('notes.workspace-panes.calendar')||'null');if(saved){if(saved.ratio>0&&saved.ratio<1)state.ratio=saved.ratio;if(saved.height>=180)state.height=saved.height;}
    if(!state.ratio){const old=Number(localStorage.getItem('notes.pane-width.calendar'));state.ratio=old>0?old/root.clientWidth:(root.clientWidth-420)/root.clientWidth;}}catch{}
   state.ratio=clamp(state.ratio||.6,.1,.9);
   let controller;const arrangement=window.PaneArrangement?.bind('panes.calendar',{state,legacy:['notes.workspace-panes.calendar','notes.pane-width.calendar'],element:root,apply:()=>controller?.refresh()});
   controller=workspace(root,{leading,trailing:slot,state,label:'calendar',breakpoint:661,proportional:true,collapsible:false,detailOnNarrow:true,minLeading:380,minTrailing:280,minHeight:180,minDetailHeight:180,
    enabled:()=>root.closest('.notes-calendar')?.classList.contains('has-event-detail'),
    onChange:value=>arrangement?.save(value)});
   const position=()=>{const panel=root.querySelector(':scope>.cal-event-panel');if(panel)slot.append(panel);controller.refresh();};
   bindings.set(root,{resize:{disconnect:()=>{arrangement?.destroy();controller.destroy();}},position});position();return;
  }
  if(spec.workspace){
   let state={width:null,height:340,collapsed:false};
   try{const saved=JSON.parse(localStorage.getItem('notes.workspace-panes.'+spec.key)||'null');if(saved&&typeof saved==='object')state={width:Number.isFinite(saved.width)&&saved.width>=240?saved.width:null,height:Number.isFinite(saved.height)&&saved.height>=140?saved.height:340,collapsed:saved.collapsed===true};else{const old=localStorage.getItem('notes.pane-width.'+spec.key);if(old!==null&&Number.isFinite(Number(old)))state.width=Number(old);}}catch{}
   let controller;const arrangement=window.PaneArrangement?.bind('panes.'+spec.key,{state,legacy:['notes.workspace-panes.'+spec.key,'notes.pane-width.'+spec.key],element:root,apply:()=>controller?.refresh()});
   controller=workspace(root,{leading,trailing:root.querySelector('.task-detail'),state,label:'task list',detailOnNarrow:true,enabled:()=>root.classList.contains('has-detail'),onChange:value=>arrangement?.save(value)});
   bindings.set(root,{resize:{disconnect:()=>{arrangement?.destroy();controller.destroy();}},position:controller.refresh});return;
  }
  const handle=document.createElement('div');handle.className='pane-divider';handle.tabIndex=0;
  handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.setAttribute('aria-label',spec.label);
  root.classList.add('split-panes');root.append(handle);
  let preferred=preferences.get(spec.key);
  if(preferred===undefined){try{const saved=localStorage.getItem('notes.pane-width.'+spec.key);if(saved!==null&&Number.isFinite(Number(saved)))preferred=Number(saved);}catch{}}
  const limits=()=>[Math.min(spec.min,root.clientWidth/2),Math.max(spec.min,root.clientWidth-spec.other)];
  function paint(value){
   const [min,max]=limits(),width=clamp(value,min,max);root.style.setProperty('--pane-width',width+'px');position();return width;
  }
  function position(){
   const visible=spec.enabled(root)&&leading.getBoundingClientRect().width>0;if(handle.hidden!==!visible)handle.hidden=!visible;
   if(!visible)return;
   const bounds=root.getBoundingClientRect(),width=leading.getBoundingClientRect().right-bounds.left;
   handle.style.left=width+'px';const [min,max]=limits();
   handle.setAttribute('aria-valuemin',Math.round(min));handle.setAttribute('aria-valuemax',Math.round(max));handle.setAttribute('aria-valuenow',Math.round(width));
  }
  let resizing=false,lastWidth=root.clientWidth;
  const arrangement=window.PaneArrangement?.bind('panes.'+spec.key,{state:preferred===undefined?{}:{width:preferred},legacy:['notes.pane-width.'+spec.key],element:root,apply:value=>{if(Number.isFinite(value.width)){preferred=value.width;if(!resizing)paint(preferred);}}});
  const save=()=>{const value=leading.getBoundingClientRect().width;preferred=value;preferences.set(spec.key,value);void arrangement?.save({width:value});};
  const stopDrag=drag(handle,{get:()=>leading.getBoundingClientRect().width,set:paint,start:()=>{resizing=true;},finish:committed=>{resizing=false;if(committed)save();}});
  const resize=new ResizeObserver(()=>{const changed=root.clientWidth!==lastWidth;lastWidth=root.clientWidth;if(changed&&!resizing&&spec.enabled(root)&&preferred!==undefined)paint(preferred);else position();});resize.observe(root);resize.observe(leading);
  bindings.set(root,{resize,position,
   valid:()=>root.querySelector(spec.leading)===leading&&handle.parentElement===root,
   destroy:()=>{arrangement?.destroy();stopDrag();resize.disconnect();handle.remove();}
  });if(preferred!==undefined)paint(preferred);else position();
 }
 function scan(){
  // A retained shell can replace a pane during background refresh. Never keep
  // measuring or observing the detached element; dispose and bind its replacement.
  for(const [root,binding] of bindings){if(!root.isConnected||binding.valid?.()===false){if(binding.destroy)binding.destroy();else binding.resize.disconnect();bindings.delete(root);}else binding.position();}
  for(const spec of specs)document.querySelectorAll(spec.selector).forEach(root=>{if(!bindings.has(root))mount(root,spec);});
 }
 let pending=false;
 const schedule=()=>{if(pending)return;pending=true;queueMicrotask(()=>{pending=false;scan();});};
 window.SplitPanes={drag,workspace,refresh:scan};
 const start=()=>{scan();new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','hidden']});};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();

import { toast } from './workbench-chrome.js';
import { EditorState } from './editor-state.js';
import { session } from './views/notes/notes-session.js';

// Per-tab recovery copies survive a reload. They are never canonical saves or
// browser-history payloads, and stay separate from shared browsing preferences.
const DraftRecovery=(()=>{
 const MAX=2*1024*1024;
 function create({storage,key}){
  let data={},serialized='';
  try{const raw=storage?.getItem(key);if(raw&&raw.length<=MAX){const saved=JSON.parse(raw);if(saved.version===1&&saved.sections&&typeof saved.sections==='object'&&!Array.isArray(saved.sections))data=saved.sections;}}catch{}
  return {read:section=>data[section],write(sections){
   const next=JSON.stringify({version:1,sections});if(next.length>MAX)throw Error('Recovery copy is too large.');
   if(next===serialized)return;
   if(!Object.keys(sections).length&&!Object.keys(data).length){serialized=next;return;}
   if(!storage)throw Error('Tab storage is unavailable.');
   if(Object.keys(sections).length)storage.setItem(key,next);else storage.removeItem(key);
   data=sections;serialized=next;
  }};
 }
 async function claimEditorIdentity(storage,namespace,{locks=typeof navigator==='undefined'?null:navigator.locks,uuid=()=>crypto.randomUUID(),onRelease=release=>window.addEventListener('pagehide',release,{once:true})}={}){
  if(!locks?.request||!storage)throw Error('Exclusive tab recovery ownership is unavailable.');
  let candidate=storage.getItem('notes.editor-tab')||uuid();
  for(let attempt=0;attempt<2;attempt++){
   const claimed=await new Promise((resolve,reject)=>{locks.request('notes-editor-tab:'+namespace+':'+candidate,{ifAvailable:true},lock=>{if(!lock){resolve(false);return;}return new Promise(release=>{onRelease(release);resolve(true);});}).catch(reject);});
   if(claimed){storage.setItem('notes.editor-tab',candidate);return candidate;}candidate=uuid();
  }
  throw Error('Another tab owns this recovery identity.');
 }
 const adapters=new Map();let store=null,namespace=null,failed=false,scheduled=false,editors=null,editorReady=Promise.resolve(true);
 function register(section,adapter){adapters.set(section,adapter);if(store)adapter.restore(store.read(section));}
 function start(value){
  if(store&&namespace===value)return editorReady;
  namespace=value;let storage;try{storage=sessionStorage;}catch{}
  store=create({storage,key:'notes.draft-recovery.v1.'+value});
  for(const [section,adapter]of adapters)adapter.restore(store.read(section));
  if (EditorState) {
   editorReady=(async()=>{
    let tab;try{tab=await claimEditorIdentity(storage,value);}catch{tab=null;}
    editors=EditorState.create({storage:EditorState.indexedStorage(!tab||typeof indexedDB==='undefined'?null:indexedDB),notify:receipt=>{document.documentElement.dataset.notesEditorRecovery=receipt.state;document.documentElement.dataset.notesEditorCheckpoint=String(Date.now());document.dispatchEvent(new Event('draft-update-ready'));}});
    const ready=await editors.start(value+':'+(tab||'unavailable'));document.documentElement.dataset.notesEditorStorage=ready?'ready':'unavailable';return ready;
   })();
  }
  return editorReady;
 }
 function checkpoint(){
  if(!store)return true;
  try{const sections={};for(const [section,adapter]of adapters){const value=adapter.capture();if(value&&Object.keys(value).length)sections[section]=value;}store.write(sections);failed=false;return true;}
  catch(error){if(!failed)toast('Could not keep a reload recovery copy. Save your changes before refreshing.');failed=true;return false;}
 }
 function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;checkpoint();});}
 if(typeof document!=='undefined'){
  for(const name of ['input','change','click'])document.addEventListener(name,schedule);
  window.addEventListener('pagehide',checkpoint);
  window.addEventListener('beforeunload',()=>{checkpoint();});
  window.addEventListener('workbench-before-update',event=>{if(!checkpoint()){event.detail?.block?.('recovery-write-failed');event.preventDefault();}});
 }
 function editorKey(node,label='editor'){
  const position=session.NotesBrowsing.currentLocation?.() ?? null,identity=position?.location||{};
  const keys=['space','page','account','sourceAccount','sourceThread','server','detail','selected','selectedEvent','thread','path','source','project','document','talk','slide','letterPath','activeFile','app','section','user','settingsPane','settingsResource','settingsSection','skillsPath','templateAffiliation','signerAffiliation'];
  return JSON.stringify([position?.view||'',Object.fromEntries(keys.filter(key=>identity[key]!==undefined).map(key=>[key,identity[key]])),label]);
 }
 return {create,claimEditorIdentity,register,start,checkpoint,editorKey,get editors(){return editors;},checkpointEditors:()=>editors?editors.checkpoint():Promise.resolve(true),hasPending(){try{return [...adapters.values()].some(a=>{const v=a.capture();return v&&Object.keys(v).length;});}catch{return true;}}};
})();

export { DraftRecovery };
window.DraftRecovery = DraftRecovery;

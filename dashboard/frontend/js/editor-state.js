'use strict';
// Storage/receipts for native editor states. No canonical save or action replay.
const EditorState=(()=>{
 const MAX=32*1024*1024,clone=value=>JSON.parse(JSON.stringify(value));
 function create({storage,notify=()=>{},schedule=setTimeout,cancel=clearTimeout,delay=180}){
  const records=new Map();let prefix='',ready=false,flight=null,timer=null,failure=null;
  async function start(value){prefix=value;try{for(const row of await storage.read(prefix))records.set(row.key,{data:row.data,owner:row.owner,version:0,saved:0,adapter:null,resumable:true});ready=true;failure=null;}catch(error){failure=error;ready=false;}return ready;}
  function touch(key){const row=records.get(key);if(!row)return;row.version++;cancel(timer);timer=schedule(()=>{timer=null;void checkpoint({prepare:false});},delay);}
  function attach(key,adapter){
   if(!key||typeof key!=='string')throw Error('An editor needs a stable recovery identity.');
   const row=records.get(key)||{version:0,saved:-1};row.adapter=adapter;row.owner=adapter.owner||'Editor';row.root=adapter.root;records.set(key,row);touch(key);
   return {touch:()=>touch(key),safe:()=>safe(key),dispose(){if(row.adapter!==adapter)return;try{row.data=clone(adapter.captureSync?adapter.captureSync():adapter.capture());row.version++;row.adapter=null;cancel(timer);timer=schedule(()=>void checkpoint({prepare:false}),delay);}catch(error){row.error=error;}}};
  }
  async function checkpoint({prepare=true}={}){
   if(flight){await flight;return checkpoint({prepare});}
   cancel(timer);timer=null;
   flight=(async()=>{
    if(!ready){if(!records.size)return true;failure||=Error('Editor recovery storage is unavailable.');return false;}
    const pending=[];
    try{
     for(const [key,row]of records){
      if(!prepare&&!row.error&&row.saved===row.version)continue;
      if(prepare&&row.adapter?.prepare&&await row.adapter.prepare()===false){row.error=Error('An editor operation has not completed.');row.reason='editor-operation-pending';return false;}
      const version=row.version;
      if(row.adapter){row.data=clone(await row.adapter.capture());row.error=null;row.reason=null;}
      if(row.data===undefined)continue;
      if(new TextEncoder().encode(JSON.stringify(row.data)).byteLength>MAX)throw Object.assign(Error('Editor recovery exceeds the available checkpoint size.'),{code:'editor-checkpoint-size'});
      pending.push({key,data:row.data,owner:row.owner,version});
     }
     await storage.write(prefix,pending);
     for(const item of pending){const row=records.get(item.key);if(row)row.saved=item.version;}
     failure=null;if(pending.length)notify({state:'checkpointed',count:pending.length});return true;
    }catch(error){failure=error;notify({state:'blocked',reason:'editor-checkpoint-failed'});return false;}
   })();try{return await flight;}finally{flight=null;}
  }
  function safe(key){const row=records.get(key);return !!(ready&&row&&!failure&&!row.error&&row.saved===row.version);}
  function covered(root){const rows=[...records.values()].filter(row=>row.adapter&&row.root&&(row.root===root||root?.contains?.(row.root)));return !!rows.length&&rows.every(row=>!row.error&&row.saved===row.version)&&!failure;}
  return {start,attach,checkpoint,safe,covered,read:key=>records.get(key)?.data,resume(key){const row=records.get(key);if(!row?.resumable)return;row.resumable=false;return row.data;},has:key=>records.has(key),touch,
   async discard(root){const keys=[...records].filter(([,row])=>row.root&&(row.root===root||root?.contains?.(row.root))).map(([key])=>key);try{for(const key of keys){await storage.remove(prefix,key);records.delete(key);}return true;}catch(error){failure=error;notify({state:'blocked',reason:'recovery-clear-failed'});return false;}},
   async beforeReload(){for(const row of records.values())if(row.adapter?.beforeReload)await row.adapter.beforeReload();},
   async cancelReload(){for(const row of records.values())await row.adapter?.cancelReload?.();},
   async forget(key){records.delete(key);await storage.remove(prefix,key);},
   status:()=>({ready,waiting:[...records.values()].filter(row=>row.saved!==row.version||row.error).map(row=>row.owner),failure:failure?'Editor recovery storage could not commit the checkpoint.':null,reason:[...records.values()].find(row=>row.reason)?.reason|| (failure?.code==='editor-checkpoint-size'?'editor-checkpoint-size':failure?.name==='QuotaExceededError'?'editor-storage-quota':!ready?'editor-storage-unavailable':null)})};
 }
 function indexedStorage(indexedDB){
  let opened;
  function open(){return opened||=(new Promise((resolve,reject)=>{if(!indexedDB){reject(Error('IndexedDB is unavailable.'));return;}const request=indexedDB.open('notes-editor-states',1);request.onupgradeneeded=()=>request.result.createObjectStore('states',{keyPath:'id'});request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);request.onblocked=()=>reject(Error('Editor storage upgrade is waiting for another tab.'));}));}
  async function transaction(mode,run){const db=await open();return new Promise((resolve,reject)=>{let tx;try{tx=db.transaction('states',mode,mode==='readwrite'?{durability:'strict'}:undefined);}catch{tx=db.transaction('states',mode);}const result=run(tx.objectStore('states'));tx.oncomplete=()=>resolve(result?.result);tx.onabort=tx.onerror=()=>reject(tx.error||Error('Editor checkpoint transaction failed.'));});}
  return {read:prefix=>transaction('readonly',store=>store.getAll()).then(rows=>(rows||[]).filter(row=>row.id.startsWith(prefix+':')).map(row=>({key:row.id.slice(prefix.length+1),data:row.data,owner:row.owner}))),write:(prefix,rows)=>transaction('readwrite',store=>{for(const row of rows)store.put({id:prefix+':'+row.key,data:row.data,owner:row.owner,updatedAt:Date.now()});}),remove:(prefix,key)=>transaction('readwrite',store=>store.delete(prefix+':'+key))};
 }
 return {create,indexedStorage};
})();

export { EditorState };
window.EditorState = EditorState;

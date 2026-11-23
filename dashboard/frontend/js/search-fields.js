/* Contextual field grammar shared by page tables, field hints and local surfaces. */
window.SearchFields=(()=>{
 const schemas={tasks:['status','type','title','due'],mail:['from','to','subject','type','account','in','is','after','before'],messages:['from','in','is','after','before'],letters:['status','type','person','target','affiliation','date'],papers:['status','type','name'],talks:['title','date'],contacts:['name','email','organization','group'],calendar:['status','title','account','after','before'],travel:['status','name','date'],apps:['status','type','name','email','server'],automations:['status','workflow','outcome'],wiki:['title','topic'],settings:['name','provider'],storage:['module','name'],'ai-models':['model','provider','feature']};
 const fold=v=>String(v??'').normalize('NFC').toLocaleLowerCase();
 const tokens=q=>q.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g)||[];
 const aliases={subject:'title',from:'sender',to:'recipients',name:'name',date:'date',outcome:'result',task:'title'};
 function parse(q){return tokens(q).map(t=>{const negative=t.startsWith('-');if(negative)t=t.slice(1);const at=t.indexOf(':');return {field:at>0?t.slice(0,at).toLowerCase():'',value:(at>0?t.slice(at+1):t).replace(/^["']|["']$/g,''),negative};});}
 function has(q){return parse(q).some(t=>t.field);}
 function matches(row,q){let groups=[[]];for(const t of parse(q)){if(!t.field&&t.value==='OR'&&!t.negative)groups.push([]);else groups.at(-1).push(t);}return groups.some(g=>g.every(t=>{if(!t.value)return true;const key=aliases[t.field]||t.field;const value=key?(row[t.field]??row[key]??(key==='name'?row.title:undefined)??(key==='title'?row.name:undefined)??''):Object.values(row).join(' ');let found=fold(value).includes(fold(t.value));if(key==='slide')found=Number(value)===Number(t.value);if(['status','type'].includes(key)){const a=key==='status'?{finished:'finish',completed:'finish',closed:'cancel',cancelled:'cancel',preparing:'prepare'}:{};const normalize=v=>a[fold(v).trim()]||fold(v).trim();found=(Array.isArray(value)?value:[value]).some(v=>normalize(v)===normalize(t.value));}if(['after','before'].includes(key)){const at=Date.parse(row.date||row.timestamp),bound=Date.parse(t.value);found=Number.isFinite(at)&&Number.isFinite(bound)&&(key==='after'?at>=bound:at<bound);}return t.negative?!found:found;}));}
 function fields(view,input){if(input?.dataset.notesSearchFields)return input.dataset.notesSearchFields.split(',');if(input?.closest('.notes-settings-page,.notes-body.settings-open'))return ['name','section'];if(input?.closest('.project-editor-layer'))return ['name','path'];if(input?.closest('.talk-inline-workspace'))return ['title','slide'];const keys=new Set(schemas[view]||['name','status','type']);const root=input?.getRootNode();for(const th of root?.querySelectorAll?.('table thead th')||[]){const label=th.querySelector('button')?.textContent||th.textContent;const key=fold(label).trim().replace(/\s+/g,'_');if(/^[a-z_]{2,30}$/.test(key))keys.add(key);}return [...keys];}
 function hint(q,view,input){const word=q.trim().toLowerCase();return word&&!/[\s:]/.test(word)?fields(view,input).filter(k=>k.startsWith(word)):[];}
 function values(q,input){
  const token=q.trim().match(/(?:^|\s)([a-z_]+):$/i);if(!token)return [];
  const set=new Set(),root=input?.getRootNode();
  for(const table of root?.querySelectorAll?.('table')||[]){const heads=[...table.querySelectorAll('thead th')].map(n=>fold(n.querySelector('button')?.textContent||n.textContent).trim().replace(/\s+/g,'_'));const i=heads.indexOf(token[1].toLowerCase());if(i<0)continue;for(const row of table.querySelectorAll('tbody>tr')){const value=row.cells[i]?.textContent.trim();if(value&&value.length<80)set.add(value);}}
  return [...set].sort().slice(0,30).map(value=>({label:value,query:q+(/\s/.test(value)?JSON.stringify(value):value)}));
 }
 function filterSurface(input,q){
  const bar=input.closest('[data-toolbar]');if(!bar||input.hasAttribute('data-search-owner'))return;
  const scope=bar.closest('.notes-settings-page,.project-editor-layer,.notes-body,.notes-apps-page')||bar.parentElement;
  // Field predicates filter mounted rows without remounting readers or editors.
  for(const table of scope.querySelectorAll('table')){
   const heads=[...table.querySelectorAll('thead th')].map(n=>fold(n.querySelector('button')?.textContent||n.textContent).trim().replace(/\s+/g,'_'));
   for(const row of table.querySelectorAll('tbody>tr')){const data={};[...row.cells].forEach((c,i)=>{data[heads[i]||String(i)]=c.textContent;});row.classList.toggle('page-search-hidden',(has(q)||input.hasAttribute('data-page-search'))&&!!q&&!matches(data,q));}
  }
  if(input.hasAttribute('data-page-search')){for(const node of scope.querySelectorAll('.talk-thumbnail-list [data-slide],.project-file-row')){const label=node.getAttribute('title')||node.querySelector('[title]')?.title||node.textContent;node.classList.toggle('page-search-hidden',!!q&&!matches({title:label,name:label,path:label,slide:node.hasAttribute('data-slide')?String(Number(node.dataset.slide)+1):''},q));}}
  if(input.hasAttribute('data-page-search'))for(const node of scope.querySelectorAll('.account-panel,.account-card,.connection-card,.storage-panel-card,.storage-panel-table tbody>tr,.ai-model-body>section,.section-settings-main>*,.section-settings-layout>nav button,.settings-nav-item,.settings-pane:not([hidden])>*,.talk-card')){if(node.contains(input))continue;const data={name:node.textContent,title:node.textContent,module:node.textContent,section:node.textContent,model:node.textContent,provider:node.textContent};node.classList.toggle('page-search-hidden',!!q&&!matches(data,q));}
 }
 return {parse,has,matches,fields,hint,values,filterSurface};
})();

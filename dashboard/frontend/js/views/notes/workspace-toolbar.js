'use strict';
// One persistent search field moves between workspace toolbars; typed queries keep focus.
let workspaceSearchFocus=null;
function workspaceSyncControl(section,busy=false){
 const label='Sync';
 return `<button type="button" id="${section}-sync" class="icon-button" aria-label="${label}" title="${label}" aria-busy="${busy}" ${busy?'disabled':''}>${WorkbenchIcons.html('cloud-check')}</button>`;
}
function paintWorkspaceSync(section,busy){
 const button=document.getElementById(section+'-sync');if(!button)return;
 button.disabled=busy;button.setAttribute('aria-busy',String(busy));
}
function workspaceContent(){
 const search=document.getElementById('workspace-search'),label=search?.closest('label'),bank=document.getElementById('workspace-search-bank');
 if(label&&bank&&label.parentElement!==bank){
  workspaceSearchFocus=document.activeElement===search?{start:search.selectionStart,end:search.selectionEnd}:null;
  bank.append(label);
 }
 return document.getElementById('workspace-content');
}
function mountWorkspaceSearch(){
 const input=document.getElementById('workspace-search'),label=input?.closest('label'),slot=document.querySelector('#workspace-content [data-workspace-search]');
 if(!label||!slot||label.parentElement===slot)return;
 slot.append(label);
 if(workspaceSearchFocus&&!label.hidden){input.focus({preventScroll:true});try{input.setSelectionRange(workspaceSearchFocus.start,workspaceSearchFocus.end);}catch{}}
 workspaceSearchFocus=null;
}
new MutationObserver(mountWorkspaceSearch).observe(document.body,{childList:true,subtree:true});

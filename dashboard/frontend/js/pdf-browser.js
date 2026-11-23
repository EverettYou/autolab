// One PDF.js reader for every Notes surface. PDF bytes remain in memory only.
import {escape, lifecycle, localURL, viewState, fa} from './content-core.js';
import * as pdfjs from '/static/vendor/notes-pdfjs/build/pdf.mjs';
import {PDFViewer, EventBus, PDFLinkService, PDFFindController} from '/static/vendor/notes-pdfjs/web/pdf_viewer.mjs';
import {textIndex} from './latex-sync.js';
import {bindGestureZoom} from '/static/js/gesture-zoom.js';
pdfjs.GlobalWorkerOptions.workerSrc='/static/vendor/notes-pdfjs/build/pdf.worker.mjs';
export function cleanPDFText(text){return String(text).normalize('NFKC').replace(/(\p{L})-\s*\n\s*(\p{L})/gu,'$1$2').replace(/\s+/g,' ').trim();}
export function pdfSelectionContext(root,selected,viewer,current){
 if(!selected||selected.isCollapsed||!selected.rangeCount||!root.contains(selected.anchorNode)||!root.contains(selected.focusNode))return null;
 const range=selected.getRangeAt(0),node=range.startContainer,card=(node.nodeType===1?node:node.parentElement)?.closest('.page[data-page-number]');
 const page=Number(card?.dataset.pageNumber)||current,view=viewer.getPageView(page-1),rect=card?.getBoundingClientRect(),first=[...range.getClientRects()].find(box=>box.width&&box.height);
 const point=view?.viewport&&rect&&first?view.viewport.convertToPdfPoint(first.left-rect.left,first.top-rect.top):null;
 const text=cleanPDFText(selected.toString());
 return text?{page,x:point?.[0]||0,y:point?view.pdfPage.view[3]-point[1]:0,text,selected:true}:null;
}
class SyncFindController extends PDFFindController{
 match(query,content,pageIndex){
  const piece=this.syncPieces?.get(pageIndex);if(!piece)return this.syncPieces?[]:super.match(query,content,pageIndex);
  const index=textIndex(content),needle=piece.text;let at=index.text.indexOf(needle),best=-1;
  while(at>=0){if(best<0||Math.abs(at-piece.offset)<Math.abs(best-piece.offset))best=at;at=index.text.indexOf(needle,at+1);}
  return best<0?[]:[{index:index.offsets[best],length:index.offsets[best+needle.length-1]+1-index.offsets[best]}];
 }
}
async function pdfSource(value){
 if(String(value).startsWith('blob:'))throw new Error('Inline PDF blobs are not supported in Notes.');
 return {url:localURL(value)};
}
export function mountPDF(host,{url,title='PDF',stateKey='',initialPage=1,onSelection,onViewChange,onReveal,initialZoom,sizeToPage=false}={}){
 if(!url)throw new Error('A PDF document URL is required.');
 const source=url,saved=viewState(stateKey),restorePage=saved.page||initialPage;
 let disposed=false,viewer,loading,pdf,readyResolve,readyReject,zoom=saved.zoom||initialZoom||1,current=saved.page||initialPage,resizeFrame,initializing=true,lastContext=null,indexPromise=null,searchSequence=0,pendingPosition=null,readingLocation=null;
 host.innerHTML=`<section class="pdf-reader" aria-label="${escape(title)} PDF viewer"><div class="pdf-reader-toolbar"><button type="button" data-prev aria-label="Previous page">${fa('previous')}</button><input data-page aria-label="Page number" inputmode="numeric" value="${current}"><span data-count>/ …</span><button type="button" data-next aria-label="Next page">${fa('next')}</button><span class="pdf-reader-spacer"></span><button type="button" data-minus aria-label="Zoom out">${fa('minus')}</button><input data-zoom aria-label="Zoom percentage" value="${Math.round(zoom*100)}%"><button type="button" data-plus aria-label="Zoom in">${fa('plus')}</button>${onReveal?`<button type="button" data-reveal aria-label="Show in Finder">${fa('folder-open')}</button>`:''}</div><div class="pdf-reader-viewport"><div class="pdf-reader-scroll"><div class="pdfViewer pdf-reader-pages"></div></div><p class="pdf-reader-status" role="status">Opening PDF…</p></div></section>`;
 const root=host.firstElementChild,q=s=>root.querySelector(s),scroll=q('.pdf-reader-scroll'),sheets=q('.pdfViewer'),status=q('[role=status]'),bus=new EventBus(),links=new PDFLinkService({eventBus:bus,externalLinkTarget:2,externalLinkRel:'noopener noreferrer'});
 root.classList.toggle('pdf-reader-page-height',sizeToPage);
 if(sizeToPage)root.style.setProperty('--pdf-reader-initial-zoom',zoom);
 const abort=new AbortController(),findController=new SyncFindController({eventBus:bus,linkService:links});
 const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject});ready.catch(()=>{});
 function paint(){if(disposed)return;const count=pdf?.numPages||0;q('[data-page]').value=current;q('[data-count]').textContent='/ '+(count||'…');q('[data-prev]').disabled=!count||current<=1;q('[data-next]').disabled=!count||current>=count;q('[data-zoom]').value=Math.round(zoom*100)+'%';viewState(stateKey,{page:current,zoom});onViewChange?.({page:current,zoom});}
 function sizePage(){
  if(!sizeToPage||disposed)return;
  const page=viewer.getPageView(current-1);if(!page?.viewport)return;
  const style=getComputedStyle(sheets),height=Math.ceil(page.viewport.height+(parseFloat(style.paddingTop)||0)+(parseFloat(style.paddingBottom)||0));
  const value=height+'px';if(root.style.getPropertyValue('--pdf-reader-page-height')!==value)root.style.setProperty('--pdf-reader-page-height',value);
 }
 function alignPage(){
  if(!sizeToPage||disposed)return;
  const page=viewer.getPageView(current-1);if(!page?.div)return;
  scroll.scrollTop+=page.div.getBoundingClientRect().top-scroll.getBoundingClientRect().top-(parseFloat(getComputedStyle(sheets).paddingTop)||0);
 }
 function fit(){if(!pdf||disposed||initializing||!scroll.clientWidth||!scroll.clientHeight)return;viewer.currentScaleValue='page-width';const base=viewer.currentScale;viewer.currentScale=base*zoom;sizePage();alignPage();}
 function go(page){if(!pdf||disposed)return;viewer.currentPageNumber=Math.max(1,Math.min(pdf.numPages,Math.trunc(Number(page)||1)));current=viewer.currentPageNumber;sizePage();alignPage();paint();}
 function changeZoom(value){zoom=Math.max(.25,Math.min(8,Number(value)||1));fit();paint();}
 function gestureZoom(factor,clientX,clientY){
  if(!pdf||disposed||initializing)return;
  const next=Math.max(.25,Math.min(8,zoom*factor));
  if(Math.abs(next-zoom)<.0005)return;
  const scaleFactor=next/zoom;zoom=next;
  // Keep the pointer/pinch midpoint stable while the scale changes.
  cancelAnimationFrame(resizeFrame);
  viewer.updateScale({scaleFactor,origin:[clientX,clientY],drawingDelay:120});
  paint();
 }
 viewer=new PDFViewer({abortSignal:abort.signal,container:scroll,viewer:sheets,eventBus:bus,linkService:links,findController,textLayerMode:1,annotationMode:pdfjs.AnnotationMode.ENABLE,annotationEditorMode:pdfjs.AnnotationEditorType.DISABLE,enableScripting:false,enableDetailCanvas:true,imagesRightClickMinSize:100,maxCanvasPixels:16*1024*1024,imageResourcesPath:'/static/vendor/notes-pdfjs/web/images/',supportsPinchToZoom:true});links.setViewer(viewer);
 bus.on('pagesinit',()=>{initializing=false;fit();go(restorePage);status.hidden=true;readyResolve(pdf);});
 bus.on('pagechanging',event=>{if(initializing)return;current=event.pageNumber;sizePage();paint();});
 bus.on('updateviewarea',event=>{const position=event.location;readingLocation={page:position.pageNumber,left:position.left,top:position.top};});
 bus.on('pagerendered',event=>{sizePage();if(event.error){status.hidden=false;status.textContent='Could not render this PDF page: '+event.error.message;}});
 const observer=new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(fit)});observer.observe(scroll);
 q('[data-prev]').onclick=()=>go(current-1);q('[data-next]').onclick=()=>go(current+1);q('[data-page]').onchange=e=>go(e.target.value);q('[data-page]').onkeydown=e=>{if(e.key==='Enter')go(e.target.value)};
 q('[data-minus]').onclick=()=>changeZoom(zoom-.25);q('[data-plus]').onclick=()=>changeZoom(zoom+.25);q('[data-zoom]').onchange=e=>changeZoom(Number(e.target.value.replace('%',''))/100);q('[data-zoom]').onkeydown=e=>{if(e.key==='Enter')changeZoom(Number(e.target.value.replace('%',''))/100)};
 if(onReveal)q('[data-reveal]').onclick=()=>onReveal();
 const clickPosition=event=>{
  const card=event.target.closest('.page[data-page-number]');if(!card)return;
  const page=Number(card.dataset.pageNumber),view=viewer.getPageView(page-1),rect=card.getBoundingClientRect();if(!view?.viewport)return;
  const point=view.viewport.convertToPdfPoint(event.clientX-rect.left,event.clientY-rect.top);
  lastContext={page,x:point[0],y:view.pdfPage.view[3]-point[1],text:event.target.closest('.textLayer span')?.textContent||'',selected:false};
 };
 root.addEventListener('pointerup',clickPosition);
 const selection=()=>{
  const scope=root.getRootNode(),selected=scope.getSelection?.()||host.ownerDocument.getSelection();
  const context=pdfSelectionContext(root,selected,viewer,current);
  if(context){lastContext=context;onSelection?.({text:context.text,page:context.page});}
 };root.addEventListener('mouseup',selection);root.addEventListener('keyup',selection);
 // Trackpad pinch (ctrl+wheel), touch pinch, and Safari gesture events.
 bindGestureZoom(scroll,gestureZoom);
 const destroy=lifecycle(host,()=>{disposed=true;searchSequence++;pendingPosition=null;root.removeEventListener('pointerup',clickPosition);abort.abort();observer.disconnect();cancelAnimationFrame(resizeFrame);root.removeEventListener('mouseup',selection);root.removeEventListener('keyup',selection);viewer.setDocument(null);links.setDocument(null);loading?.destroy();readyResolve(null);});
 (async()=>{
  const input=await pdfSource(source);if(disposed)return;
  loading=pdfjs.getDocument({...input,cMapUrl:'/static/vendor/notes-pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/static/vendor/notes-pdfjs/standard_fonts/',wasmUrl:'/static/vendor/notes-pdfjs/wasm/',isEvalSupported:false,enableXfa:false});
  loading.onPassword=()=>{loading.destroy();const error=new Error('This PDF requires a password. Open an unlocked copy.');status.textContent=error.message;readyReject(error);};
  const document=await loading.promise;if(disposed){document.destroy();return;}pdf=document;links.setDocument(pdf);viewer.setDocument(pdf);paint();
 })().catch(error=>{if(!disposed){status.hidden=false;status.textContent='Could not open PDF: '+error.message;readyReject(error);}});

 async function documentIndex(){
  if(!indexPromise)indexPromise=(async()=>{await ready;if(!pdf||disposed)return [];const rows=[];let size=0;
   if(pdf.numPages>2000)throw Error('This document is too long for text fallback. Compile to use SyncTeX.');
   for(let page=1;page<=pdf.numPages;page++){if(disposed)throw Error('PDF reader closed.');const sheet=await pdf.getPage(page),content=await sheet.getTextContent();
    const height=sheet.view[3],text=content.items.filter(item=>item.str&&item.transform[5]>=35&&item.transform[5]<=height-35).map(item=>item.str+(item.hasEOL?'\n':' ')).join('');
    const normalized=textIndex(text).text;size+=normalized.length;if(size>12000000)throw Error('PDF text index exceeds the memory limit. Compile to use SyncTeX.');rows.push({page,text:normalized});
   }return rows;})();
  return indexPromise;
 }
 async function findText(text,{pageHint=current,highlight=true,screenY}={}){
  const sequence=++searchSequence,rows=await documentIndex();if(disposed||sequence!==searchSequence)return {matched:false};
  const combined=rows.map(row=>row.text).join(''),full=textIndex(text).text.slice(0,1200),words=text.match(/[\p{L}\p{N}]+/gu)||[],candidates=[full,...[10,6].filter(n=>words.length>n).map(n=>textIndex(words.slice(0,n).join(' ')).text)];
  let start=-1,needle='',partial=false;
  for(const candidate of candidates){if(candidate.length<12)continue;const positions=[];for(let at=combined.indexOf(candidate);at>=0&&positions.length<30;at=combined.indexOf(candidate,at+1))positions.push(at);if(!positions.length)continue;
   let hint=0;for(const row of rows){if(row.page===pageHint)break;hint+=row.text.length;}
   start=positions.sort((a,b)=>Math.abs(a-hint)-Math.abs(b-hint))[0];needle=candidate;partial=candidate!==full;break;
  }
  if(start<0)return {matched:false};
  const pieces=new Map();let offset=0;for(const row of rows){const a=Math.max(start,offset),b=Math.min(start+needle.length,offset+row.text.length);if(b>a)pieces.set(row.page-1,{text:row.text.slice(a-offset,b-offset),offset:a-offset});offset+=row.text.length;}
  const page=[...pieces.keys()][0]+1;
  if(!highlight){
   const sheet=await pdf.getPage(page),content=await sheet.getTextContent(),height=sheet.view[3],offset=pieces.get(page-1).offset;let count=0,target;
   for(const item of content.items){if(!item.str||item.transform[5]<35||item.transform[5]>height-35)continue;const size=textIndex(item.str).text.length;if(count+size>offset){target=item;break;}count+=size;}
   await goToPosition({page,x:target?.transform[4]||0,y:target?height-target.transform[5]:0,screenY});return {matched:true,page,pages:[page],partial};
  }
  pendingPosition=null;findController.syncPieces=pieces;go(page);
  bus.dispatch('find',{source:root,type:'',query:text,caseSensitive:false,entireWord:false,highlightAll:true,findPrevious:false,matchDiacritics:false});
  return {matched:true,page,pages:[...pieces.keys()].map(p=>p+1),partial};
 }
 function alignPosition(){
  if(!pendingPosition||disposed)return;
  const view=viewer.getPageView(pendingPosition.page-1);if(!view?.viewport||!view.pdfPage)return;
  const [,y]=view.viewport.convertToViewportPoint(pendingPosition.x,view.pdfPage.view[3]-pendingPosition.y),bounds=scroll.getBoundingClientRect();
  const desired=Math.max(bounds.top+20,Math.min(bounds.bottom-20,pendingPosition.screenY??bounds.top+bounds.height/2));
  scroll.scrollTop+=view.div.getBoundingClientRect().top+y-desired;pendingPosition=null;
 }
 bus.on('pagerendered',alignPosition);bus.on('textlayerrendered',alignPosition);
 async function goToPosition(position){await ready;if(disposed)return;findController.syncPieces=null;bus.dispatch('findbarclose',{source:root});pendingPosition=position;go(position.page);alignPosition();}
 async function getSyncContext(){await ready;if(!pdf||disposed)return null;if(lastContext&&(lastContext.selected||lastContext.page===current))return {...lastContext};const text=await(await pdf.getPage(current)).getTextContent();const item=text.items.find(item=>item.str?.trim().length>35);return {page:current,x:item?.transform[4]||0,y:item?((await pdf.getPage(current)).view[3]-item.transform[5]):0,text:item?.str||'',selected:false};}
 function getReadingPosition(){
  if(!pdf||disposed||initializing)return null;
  // Flush a wheel scroll that PDF.js has not processed yet. Coordinates are
  // relative to the first visible PDF page, including the page's top margin.
  viewer.update();
  const page=readingLocation?.page||current,view=viewer.getPageView(page-1),bounds=scroll.getBoundingClientRect(),sheet=view?.div.getBoundingClientRect();
  return {...(readingLocation||{page}),zoom,scrollTop:scroll.scrollTop,scrollLeft:scroll.scrollLeft,
   ...(sheet?{offsetX:bounds.left-sheet.left,offsetY:bounds.top-sheet.top,pageWidth:sheet.width,pageHeight:sheet.height}:{})};
 }
 function restoreReadingPosition(position){
  if(!pdf||disposed||initializing||!position)return false;
  // This restoration fits the current pane itself. An already queued resize
  // fit would refit once more and can clamp horizontal scrolling back to zero.
  cancelAnimationFrame(resizeFrame);
  const page=Math.max(1,Math.min(pdf.numPages,Math.trunc(Number(position.page)||1)));
  if(Number.isFinite(position.zoom)&&position.zoom>0)changeZoom(position.zoom);
  pendingPosition=null;
  if(Number.isFinite(position.offsetX)&&Number.isFinite(position.offsetY)&&position.pageWidth>0&&position.pageHeight>0){
   go(page);
   const sheet=viewer.getPageView(page-1).div.getBoundingClientRect(),bounds=scroll.getBoundingClientRect();
   scroll.scrollTop+=sheet.top-bounds.top+position.offsetY*sheet.height/position.pageHeight;
   scroll.scrollLeft+=sheet.left-bounds.left+position.offsetX*sheet.width/position.pageWidth;
  }else if(Number.isFinite(position.left)&&Number.isFinite(position.top)){
   viewer.scrollPageIntoView({pageNumber:page,destArray:[null,{name:'XYZ'},position.left,position.top,null],allowNegativeOffset:true,ignoreDestinationZoom:true});
  }else{
   go(page);
   if(Number.isFinite(position.scrollTop))scroll.scrollTop=position.scrollTop;
   if(Number.isFinite(position.scrollLeft))scroll.scrollLeft=position.scrollLeft;
  }
  // Publish the restored location before a later resize/zoom refit so that
  // PDF.js preserves the new scroll position instead of its initial page.
  viewer.update();current=viewer.currentPageNumber;paint();return true;
 }
 return {getSyncContext,goToPosition,findText,getReadingPosition,restoreReadingPosition,root,ready,destroy,goToPage:go,setZoom:changeZoom,pause(){},resume(){requestAnimationFrame(()=>{if(!disposed){viewer.update();fit();}})},weight:()=>viewer._buffer?.size||1,async getText(page=current){await ready;if(!pdf||disposed)return '';const content=await(await pdf.getPage(page)).getTextContent();return cleanPDFText(content.items.map(item=>item.str+(item.hasEOL?'\n':' ')).join(''));}};
}

// Small first-page covers share the reader's PDF.js runtime and worker.
// Covers are decorative; the full viewer retains selectable text and zoom.
export async function pdfCover(url,{width=168,height=116}={}){
 const loading=pdfjs.getDocument({...await pdfSource(url),cMapUrl:'/static/vendor/notes-pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/static/vendor/notes-pdfjs/standard_fonts/',wasmUrl:'/static/vendor/notes-pdfjs/wasm/',isEvalSupported:false,enableXfa:false});
 loading.onPassword=()=>loading.destroy();
 const timeout=setTimeout(()=>loading.destroy(),20000);
 try{
  const doc=await loading.promise,page=await doc.getPage(1),base=page.getViewport({scale:1});
  const ratio=Math.min(window.devicePixelRatio||1,2),viewport=page.getViewport({scale:Math.min(width/base.width,height/base.height)*ratio});
  const canvas=document.createElement('canvas');canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
  await page.render({canvasContext:canvas.getContext('2d'),viewport,background:'#ffffff'}).promise;
  return canvas.toDataURL('image/png');
 }finally{clearTimeout(timeout);await loading.destroy();}
}

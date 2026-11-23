// Bounded, offset-preserving text matching shared by source and PDF synchronization.
export function stripLatex(source){
 return String(source).replace(/(?<!\\)%[^\n]*/g,m=>' '.repeat(m.length))
  .replace(/\\(?:cite\w*|(?:eq|page|auto|[cC])?ref|label|begin|end|includegraphics|bibliography|bibliographystyle|input|include)(?:\[[^\]]*\])*\{[^}]*\}/g,m=>' '.repeat(m.length))
  .replace(/\\[a-zA-Z@]+\*?/g,m=>' '.repeat(m.length)).replace(/[{}$]/g,' ');
}
export function textIndex(text){
 const chars=[],offsets=[];let position=0;
 for(const char of String(text)){
  for(const normalized of char.normalize('NFKD').toLowerCase())if(/[\p{L}\p{N}]/u.test(normalized)){chars.push(normalized);offsets.push(position);}
  position+=char.length;
 }
 return {text:chars.join(''),offsets};
}
export function textMatches(source,query,{latex=false,limit=20}={}){
 const index=textIndex(latex?stripLatex(source):source),needle=textIndex(query).text,matches=[];
 if(needle.length<8)return matches;
 for(let at=index.text.indexOf(needle);at>=0&&matches.length<limit;at=index.text.indexOf(needle,at+1))matches.push({from:index.offsets[at],to:index.offsets[at+needle.length-1]+1});
 return matches;
}
// PDF citation labels have no literal counterpart to LaTeX \cite/\ref commands.
// Try the unmodified quotation first, since numeric brackets may also be math.
function sourceQuery(query){return String(query).replace(/\[(?:A?\d+)(?:\s*(?:[,;]|[-–—])\s*A?\d+)*\]/g,' ');}
export function sourceMatches(source,query,{limit=20}={}){
 const literal=textMatches(source,query,{latex:true,limit});if(literal.length)return literal;
 const clean=sourceQuery(query),exact=textMatches(source,clean,{latex:true,limit});
 if(exact.length)return exact;
 const index=textIndex(stripLatex(source)),needle=textIndex(clean).text;
 if(needle.length<96||needle.length>100000)return [];
 // Longer anchors reduce collisions; shorter ones tolerate a nearby formula
 // or extraction artifact. Both edges must match, in order and at a plausible distance.
 const sizes=[96,64,40,...Array.from({length:13},(_,i)=>24-i)];
 for(const headSize of sizes)for(const tailSize of sizes){
  if(needle.length<headSize+tailSize||Math.min(headSize,tailSize)<24&&headSize+tailSize<64)continue;
  const head=needle.slice(0,headSize),tail=needle.slice(-tailSize),matches=[];
  let candidates=0;
  for(let start=index.text.indexOf(head);start>=0;start=index.text.indexOf(head,start+1)){
   if(++candidates>200)return []; // Refuse repetitive anchors rather than truncate ambiguity.
   const minEnd=start+Math.max(headSize,Math.floor(needle.length*.5)-tailSize);
   const maxEnd=start+Math.min(100000,Math.ceil(needle.length*1.75)+256)-tailSize;
   for(let end=index.text.indexOf(tail,minEnd);end>=0&&end<=maxEnd;end=index.text.indexOf(tail,end+1)){
    // A short edge is useful beside math, but also needs interior evidence.
    if(Math.min(headSize,tailSize)<24){
     let supported=false;
     for(const fraction of [.25,.5,.75]){
      const at=Math.floor((needle.length-24)*fraction),piece=needle.slice(at,at+24),found=index.text.indexOf(piece,start+headSize);
      if(found>=0&&found+24<=end){supported=true;break;}
     }
     if(!supported)continue;
    }
    matches.push({from:index.offsets[start],to:index.offsets[end+tailSize-1]+1});
    if(matches.length>=limit)return matches;
   }
  }
  if(matches.length)return matches;
 }
 return [];
}
export function sourceSnippet(source,selection){
 if(selection.to>selection.from)return stripLatex(source.slice(selection.from,selection.to)).trim().slice(0,1800);
 const clean=stripLatex(source),lineStart=clean.lastIndexOf('\n',selection.head-1)+1,lineEnd=clean.indexOf('\n',selection.head),line=clean.slice(lineStart,lineEnd<0?clean.length:lineEnd).trim();
 if(textIndex(line).text.length>=12)return line.slice(0,1200);
 return clean.slice(Math.max(0,selection.head-100),selection.head+220).trim();
}
export function chooseSourceMatch(source,query,line){
 const matches=sourceMatches(source,query);
 if(line){
  const distance=match=>{const first=source.slice(0,match.from).split('\n').length,last=first+source.slice(match.from,match.to).split('\n').length-1;return Math.max(first-line,line-last,0);};
  const nearby=matches.map(match=>({match,distance:distance(match)})).filter(item=>item.distance<=20).sort((a,b)=>a.distance-b.distance);
  if(nearby.length===1||nearby.length>1&&nearby[0].distance<nearby[1].distance)return nearby[0].match;
 }
 return matches.length===1?matches[0]:null;
}

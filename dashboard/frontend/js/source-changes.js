// A conservative three-way merge: each side's changes occupy one enclosing
// range. Overlapping ranges require review, even if a finer diff could merge.
export function sourceChange(before,after){
 let from=0,to=before.length,end=after.length;
 while(from<to&&from<end&&before[from]===after[from])from++;
 while(to>from&&end>from&&before[to-1]===after[end-1]){to--;end--;}
 return {from,to,insert:after.slice(from,end)};
}
export function mergeSourceChanges(base,local,remote){
 if(local===remote||remote===base)return local;
 if(local===base)return remote;
 const a=sourceChange(base,local),b=sourceChange(base,remote);
 if(!(a.to<b.from||b.to<a.from))return null;
 const [first,last]=a.from<b.from?[a,b]:[b,a];
 return base.slice(0,first.from)+first.insert+base.slice(first.to,last.from)+last.insert+base.slice(last.to);
}

'use strict';
const $=id=>document.getElementById(id), ns='http://www.w3.org/2000/svg';
let doc='demo',data=null,selected=null,view='compare',box=[0,0,2384,1684],reviews={},busy=false,demoAvailable=true;
const colors={signal:'#087f8c',boundary:'#b46b14',unknown:'#7c66aa'};
const names={dashed:'Dashed',dotted:'Dotted',dash_dot:'Dash-dot',dash_double_dot:'Dash-double-dot',unclassified_dashed:'V1 unclassified'};
function node(tag,attrs={}){const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;}
function pageOptions(n,p=4){$('page').replaceChildren(...Array.from({length:n},(_,i)=>new Option(`${i+1}${doc==='demo'&&i<3?' · legend':''}`,i+1)));$('page').value=Math.min(p,n);}
function query(){return new URLSearchParams({doc,page:$('page').value,mode:$('method').value}).toString();}
function key(){return data?`dottedline-v2:${data.document_sha256}:${data.page}:${data.mode}:${data.detector_revision||'legacy'}`:'';}
function persist(){try{localStorage.setItem(key(),JSON.stringify(reviews));}catch{$('status').textContent='Browser storage is full. Export to keep your review.';}}
function reviewed(l){return {...l,...reviews[l.id]};}
function category(l){const t=reviewed(l).engineering_type;return t.includes('boundary')?'boundary':t.includes('signal')?'signal':'unknown';}
function visible(l){const f=$('filter').value;return f==='rejected'?reviewed(l).review==='rejected':f==='all'||(f==='boundary'?category(l)==='boundary':category(l)!=='boundary');}
function status(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
function lock(value){busy=value;$('loading').hidden=!value;for(const id of ['analyze','export','file','page','method','demo'])$(id).disabled=value;$('demo').disabled=value||!demoAvailable;}
async function analyze(){
 lock(true);status('Reading strokes and checking gap patterns…');
 try{
  const response=await fetch('/api/analyze?'+query());const result=await response.json();if(!response.ok)throw Error(result.error||'Analysis failed.');
  const url='/api/source.png?'+query();await new Promise((resolve,reject)=>{const im=new Image();im.onload=resolve;im.onerror=()=>reject(Error('Drawing preview could not load.'));im.src=url;});
  data=result;selected=null;try{reviews=JSON.parse(localStorage.getItem(key())||'{}');}catch{reviews={};}
  for(const id of ['source','before']){const el=$(id);el.setAttribute('href',url);el.setAttribute('width',data.width);el.setAttribute('height',data.height);}
  $('paper').setAttribute('width',data.width);$('paper').setAttribute('height',data.height);
  $('count').textContent=`${data.lines.length} candidate runs`;
  const boundaries=data.lines.filter(l=>category(l)==='boundary').length;
  $('summary').textContent=`${boundaries} boundary runs · ${data.mode==='v1'?'V1 baseline':data.mode==='native'?'Native PDF geometry':'Raster reconstruction'} · no junctions inferred`;
  $('warnings').textContent=data.warnings.join(' ');fit();draw();inspect();
  status(`Page ${data.page} ready · review saved in this browser`);
 }catch(e){status(e.message,true);}finally{lock(false);$('export').disabled=!data;}
}
function setBox(){
 $('drawing').setAttribute('viewBox',box.join(' '));
 const x=box[0]+box[2]*Number($('split').value)/100;
 const clip=$('clipRect');clip.setAttribute('x',-10000);clip.setAttribute('y',-10000);clip.setAttribute('width',Math.max(0,x+10000));clip.setAttribute('height',30000);
 const line=$('divider');for(const [k,v] of Object.entries({x1:x,x2:x,y1:box[1],y2:box[1]+box[3]}))line.setAttribute(k,v);
}
function fit(){if(!data)return;const points=data.lines.filter(visible).flatMap(l=>l.points);if(!points.length){box=[0,0,data.width,data.height];}else{const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const x=Math.min(...xs),y=Math.min(...ys),w=Math.max(100,Math.max(...xs)-x),h=Math.max(100,Math.max(...ys)-y);box=[x-50,y-50,w+100,h+100];}setBox();}
function draw(){
 if(!data)return;$('traces').replaceChildren();$('hits').replaceChildren();$('lines').replaceChildren();
 const items=data.lines.filter(visible);
 for(const l of items){const r=reviewed(l),c=colors[category(l)],p=l.points;
  const attrs={x1:p[0][0],y1:p[0][1],x2:p[1][0],y2:p[1][1]};
  const trace=node('line',{...attrs,stroke:c,class:`trace ${selected===l.id?'selected':''} ${r.review==='rejected'?'rejected':''}`});$('traces').append(trace);
  const hit=node('line',{...attrs,class:'hit','data-line':l.id});hit.addEventListener('click',()=>select(l.id));$('hits').append(hit);
  const button=document.createElement('button');button.className='candidate';button.setAttribute('aria-pressed',String(l.id===selected));button.dataset.id=l.id;
  const dot=document.createElement('span');dot.className='dot';dot.style.background=c;const id=document.createElement('strong');id.textContent=l.id;
  const label=document.createElement('span');label.textContent=names[l.style]||l.style;
  const mark=document.createElement('small');mark.textContent=r.review==='accepted'?'Accepted':r.review==='rejected'?'Rejected':category(l)==='boundary'?'Boundary':`${l.fragment_count} strokes`;
  button.append(dot,id,label,mark);button.onclick=()=>select(l.id,true);$('lines').append(button);
 }
 if(!items.length){const p=document.createElement('p');p.textContent='No candidates in this view. Try another filter or page.';$('lines').append(p);}
 $('listCount').textContent=`${items.length} shown`;
 $('source').setAttribute('opacity',view==='trace'?'0':view==='overlay'?'.32':'1');
 $('before').style.display=view==='compare'?'':'none';$('divider').style.display=view==='compare'?'':'none';
 $('compareControl').hidden=view!=='compare';$('leftLabel').hidden=view!=='compare';$('rightLabel').textContent=view==='compare'?'Continuous geometry':view==='trace'?'Continuous trace + retained meaning':'Semantic overlay';
 setBox();
}
function select(id,focus=false){selected=id;draw();inspect();if(focus){const l=data.lines.find(l=>l.id===id),[p,q]=l.points,w=Math.abs(q[0]-p[0]),h=Math.abs(q[1]-p[1]);const pad=Math.max(40,Math.max(w,h)*.18);box=[Math.min(p[0],q[0])-pad,Math.min(p[1],q[1])-pad,Math.max(80,w)+2*pad,Math.max(80,h)+2*pad];setBox();}}
function inspect(){
 const l=data?.lines.find(l=>l.id===selected);$('inspector').hidden=!l;$('selectedEmpty').hidden=!!l;if(!l)return;
 const r=reviewed(l);$('lineId').textContent=l.id;$('pattern').textContent=names[l.style]||l.style;
 $('facts').replaceChildren();
 const support=l.support?.kind==='matching_pattern_at_endpoint'?`Matching endpoint: ${l.support.line_ids.join(', ')}`:'Repeated local pattern';
 for(const [label,value] of [['Observed strokes',l.fragment_count],['Geometry score',l.geometry_score.toFixed(3)],['Detection support',l.support?support:'V1 baseline'],['Median gap',`${l.median_gap_pt.toFixed(2)} pt`],['Span',`${l.length_pt.toFixed(1)} pt`],['Meaning',r.engineering_type.replaceAll('_',' ')],['Connections','Not inferred']]){const dt=document.createElement('dt');dt.textContent=label;const dd=document.createElement('dd');dd.textContent=value;$('facts').append(dt,dd);}
 $('evidence').textContent=reviews[l.id]?.engineering_type?`User assigned. ${r.note||'No evidence note added.'}`:l.semantic_evidence?`${l.semantic_status.replaceAll('_',' ')} · page ${l.semantic_evidence.page}: ${l.semantic_evidence.text} ${l.semantic_evidence.basis}`:'No engineering meaning assigned. Pattern recognition alone cannot establish the signal medium.';
 $('meaning').value=reviews[l.id]?.engineering_type||'preserve';$('note').value=reviews[l.id]?.note||'';$('reviewStatus').textContent=`Review: ${r.review}. Accepting geometry does not verify plant connectivity.`;
 $('patternPreview').replaceChildren();const svg=$('patternPreview'),col=colors[category(l)],start=l.points[0];
 const frag=l.observed_fragments||[];const scale=250/Math.max(1,l.length_pt);
 if(frag.length){for(const f of frag){const d=p=>Math.hypot(p[0]-start[0],p[1]-start[1])*scale;svg.append(node('line',{x1:10+d(f.points[0]),x2:10+d(f.points[1]),y1:14,y2:14,stroke:col,'stroke-width':2}));}}
 else svg.append(node('line',{x1:10,x2:260,y1:14,y2:14,stroke:col,'stroke-width':2,'stroke-dasharray':'12 6'}));
 svg.append(node('line',{x1:10,x2:260,y1:39,y2:39,stroke:col,'stroke-width':2}));
}
function edit(values){if(!selected)return;reviews[selected]={...reviews[selected],...values};persist();draw();inspect();}
$('meaning').onchange=()=>{if(!selected)return;if($('meaning').value==='preserve'){if(reviews[selected])delete reviews[selected].engineering_type;persist();draw();inspect();}else edit({engineering_type:$('meaning').value,note:$('note').value});};
$('note').onchange=()=>edit({note:$('note').value});$('accept').onclick=()=>edit({review:'accepted'});$('reject').onclick=()=>edit({review:'rejected'});$('reset').onclick=()=>{delete reviews[selected];persist();draw();inspect();};
$('analyze').onclick=analyze;$('page').onchange=analyze;$('method').onchange=analyze;
$('file').onchange=async()=>{if(!$('file').files[0])return;lock(true);status('Opening drawing…');try{const f=$('file').files[0],body=new FormData();body.append('file',f);const response=await fetch('/api/upload',{method:'POST',body});const result=await response.json();if(!response.ok)throw Error(result.error);doc=result.id;$('filename').textContent=result.name;pageOptions(result.pages,1);await analyze();}catch(e){status(e.message,true);}finally{lock(false);}};
$('demo').onclick=()=>{doc='demo';$('filename').textContent='2401 P&ID · 12 pages';pageOptions(12);analyze();};
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>{view=button.dataset.view;document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));draw();};
$('filter').onchange=()=>{draw();fit();};$('fit').onclick=fit;$('full').onclick=()=>{if(data){box=[0,0,data.width,data.height];setBox();}};$('split').oninput=setBox;
function zoom(factor,cx=.5,cy=.5){const w=box[2]*factor,h=box[3]*factor;if(w<12||w>30000)return;box=[box[0]+(box[2]-w)*cx,box[1]+(box[3]-h)*cy,w,h];setBox();}
$('zoomIn').onclick=()=>zoom(.75);$('zoomOut').onclick=()=>zoom(1.333);
$('drawing').addEventListener('wheel',e=>{e.preventDefault();const r=$('drawing').getBoundingClientRect();zoom(e.deltaY>0?1.12:.89,(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height);},{passive:false});
let drag=null;$('drawing').onpointerdown=e=>{if(e.target.classList.contains('hit'))return;drag={x:e.clientX,y:e.clientY,box:[...box]};$('drawing').setPointerCapture(e.pointerId);};$('drawing').onpointermove=e=>{if(!drag)return;const r=$('drawing').getBoundingClientRect(),scale=Math.min(r.width/drag.box[2],r.height/drag.box[3]);box=[drag.box[0]-(e.clientX-drag.x)/scale,drag.box[1]-(e.clientY-drag.y)/scale,...drag.box.slice(2)];setBox();};$('drawing').onpointerup=$('drawing').onpointercancel=()=>drag=null;
$('export').onclick=async()=>{if(!data)return;lock(true);$('loading').hidden=true;status('Preparing images and semantic JSON…');try{const q=new URLSearchParams({doc,page:data.page,mode:data.mode==='raster'?'raster':data.mode});const response=await fetch('/api/export?'+q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reviews,detector_revision:data.detector_revision,accepted_only:$('acceptedOnly').checked})});if(!response.ok)throw Error((await response.json()).error);const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download=`dottedline-page-${data.page}-${data.mode}.zip`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status('AI package downloaded. Keep the JSON with the images.');}catch(e){status(e.message,true);}finally{lock(false);}};
async function initialize(){
 pageOptions(12);
 try{
  const response=await fetch('/health');if(!response.ok)throw Error('Unable to reach the local server.');
  demoAvailable=(await response.json()).demo_available!==false;
  if(demoAvailable){await analyze();return;}
  $('filename').textContent='Choose a PDF or image';$('page').replaceChildren(new Option('1','1'));
  for(const id of ['analyze','export','demo'])$(id).disabled=true;
  $('selectedEmpty').textContent='Open a drawing to detect and review its line patterns.';
  status('Ready · open a drawing to begin');
 }catch(e){status(e.message,true);}
}
initialize();

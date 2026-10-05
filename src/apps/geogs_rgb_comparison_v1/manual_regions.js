const root='/data/p2p3_manual_regions_v1/';
const el=id=>document.getElementById(id);
let data, sequence=0;
function showError(error){el('error').hidden=false;el('error').textContent='도면을 불러오지 못했습니다: '+error.message;}
function draw(){
  const region=el('region').value, sourceMode=el('mode').value==='sources';
  const row=(sourceMode?data.sources:data.views).find(v=>v.train_index===Number(el('view-select').value));
  if(!row)return;
  const path=root+region+'/'+(sourceMode?row.image:'frames/'+String(row.train_index).padStart(3,'0')+'.jpg');
  el('frame-label').textContent=region+' · '+row.name+' · '+(sourceMode?'수동 기준 영상':row.manual_source?'수동 기준 영상':'MVS 대응을 검사한 전파 영상');
  el('frame').src=path;el('frame-link').href=path;
  el('frame').onerror=()=>showError(Error('선택한 이미지'));
}
function options(preferred){
  const rows=el('mode').value==='sources'?data.sources:data.views;
  el('view-select').replaceChildren(...rows.map(row=>{
    const option=document.createElement('option');option.value=row.train_index;
    option.textContent=String(row.train_index).padStart(3,'0')+' · '+row.name+' · R1 '+Number(row.native_counts['1']).toLocaleString()+' native px';return option;
  }));if(rows.some(row=>row.train_index===preferred))el('view-select').value=preferred;draw();
}
async function load(){
  const id=++sequence,region=el('region').value;
  try{
    el('error').hidden=true;
    const response=await fetch(root+region+'/review.json',{cache:'no-store'});
    if(!response.ok)throw Error('HTTP '+response.status);
    const value=await response.json();if(id!==sequence)return;data=value;
    const supported=data.views.filter(v=>v.native_counts['1']>0).length;
    el('summary').textContent=region+' · 기준 영상 '+data.sources.length+'장 · 전체 '+data.views.length+'장 생성 · R1 유효 표본이 있는 영상 '+supported+'장. '+(region==='P2'?'R1: 반복 아치 구조가 있는 대상 지붕.':'R1: 긴 곡면 지붕과 전면 외벽. 수직뷰 지붕의 결측은 그대로 제외.');
    el('sources-pdf').href=root+region+'/'+region+'_manual_sources_native_weights.pdf';
    el('all-pdf').href=root+region+'/'+region+'_all_views.pdf';options(Number(new URLSearchParams(location.search).get('view')));
  }catch(error){if(id===sequence)showError(error);}
}
el('region').addEventListener('change',load);el('mode').addEventListener('change',()=>data&&options());el('view-select').addEventListener('change',draw);
const requested=new URLSearchParams(location.search).get('region');if(['P2','P3'].includes(requested))el('region').value=requested;
if(new URLSearchParams(location.search).get('mode')==='all')el('mode').value='all';
load();

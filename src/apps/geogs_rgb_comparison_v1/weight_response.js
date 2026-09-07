const base='/data/weight_response_v1/';
const $=id=>document.getElementById(id), fmt=n=>n==null?'유효값 없음':n.toFixed(3), percent=n=>(100*n).toFixed(1)+'%';
let data,generation=0,objectURL;
const qa=window.__WEIGHT_RESPONSE_QA__={ready:false,errors:[]};
function fail(error){qa.ready=false;qa.errors.push(String(error));$('error').hidden=false;$('error').textContent=String(error);$('status').textContent='자료 확인 실패';}
async function show(){
 const ticket=++generation;qa.ready=false;$('status').textContent='그림을 확인하는 중입니다.';
 const region=$('region').value,rr=data.regions[region],view=rr.views.find(v=>v.id===$('view-select').value),e=rr.exposure['4'],s=view.stats['4'];
 $('camera').textContent=region+' · '+view.name;
 $('exposure').textContent=`22,000회 중 R1이 있는 카메라 선택 ${e.r1_steps.toLocaleString()}회 (${e.r1_cameras}/${e.train_cameras}개 카메라). 이 영상은 ${e.selected_view_visits[view.name]}회 선택됐습니다. 세 가중치 조건의 선택 횟수는 같습니다. 같은 지붕점이 이 모든 관측에서 보인다는 뜻은 아닙니다.`;
 let explanation=region==='P1'?'R1 중앙값도 2m 이상으로 남아 있어 보정 대상 대부분의 불일치가 남습니다. 가중치 증가만으로 보정과 주변 보존을 동시에 해결했는지 따로 확인해야 합니다.':region==='P2'?'가중치 0→1의 큰 변화는 반복된 지붕 구조 양옆의 넓은 지붕 면에서 확인됩니다. 1→4의 추가 차이는 아래 0–0.5m 색상 범위와 예시 B로 확인하세요.':'0046_D 사선뷰에서는 가중치 0→1에서 크게 반응합니다. 이 수치는 외벽이 보이는 해당 영상의 전체 R1 집계이며, 모든 픽셀을 외벽으로 별도 분류한 값은 아닙니다.';
 if(region==='P3'&&view.id==='source_4')explanation=`앞선 “지붕에 3.2m 불일치가 남는다”는 해석을 정정합니다. 평균은 ${fmt(s.mae_m)}m지만 중앙값은 ${(100*s.median_m).toFixed(2)}cm입니다. 10m를 넘는 ${s.gt_10_count.toLocaleString()}픽셀(${percent(s.gt_10_fraction)})이 절대잔차 합의 ${percent(s.gt_10_share_of_abs_error)}를 차지합니다. 유효 표본 대부분의 작은 잔차, 일부 큰 불일치, depth 결측을 나누어 해석해야 합니다. 큰 잔차만으로 MVS 오류나 prior 오류를 확정하지 않습니다.`;
 $('interpretation').textContent=explanation;
 $('metrics').innerHTML=[0,1,4].map(a=>{const v=view.stats[a];return `<tr><td>${a}</td><td>${fmt(v.mae_m)} m</td><td>${fmt(v.median_m)} m</td><td>${fmt(v.p95_m)} m</td><td>${percent(v.le_01_fraction)}</td></tr>`}).join('');
 $('scope').textContent=`R1 전체 ${view.r1_pixels.toLocaleString()}픽셀을 집계했습니다. 이 중 MVS 점이 기존 3D 표시 범위 안에 있는 것은 ${view.roi_pixels.toLocaleString()}픽셀이며, 그 부분의 가중치 4 평균은 ${fmt(view.roi_stats['4'].mae_m)}m입니다. 그림은 R1 전체를 표시합니다. 표시 범위 밖이라는 이유만으로 잘못된 관측으로 판정하지 않습니다.`;
 $('probes').innerHTML=view.probes.map(p=>`<tr><td>${p.label} (${p.x}, ${p.y})</td><td>${fmt(p.MVS)}</td><td>${fmt(p.prior)}</td><td>${fmt(p.GS['0'])}</td><td>${fmt(p.GS['1'])}</td><td>${fmt(p.GS['4'])}</td><td>${p.in_viewer_roi?'범위 안':'범위 밖'}</td></tr>`).join('');
 $('result-link').href='./weights.html?region='+region;
 const params=new URLSearchParams({region,view:view.id});history.replaceState(null,'','?'+params);
 const address=base+view.figure;$('figure-link').href=address;
 const response=await fetch(address);if(!response.ok)throw Error('그림 HTTP '+response.status);
 const bytes=await response.arrayBuffer(),digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
 if(digest!==view.figure_sha256)throw Error('그림 SHA256 불일치');if(ticket!==generation)return;
 const nextURL=URL.createObjectURL(new Blob([bytes],{type:'image/png'})),frame=new Image();frame.id='frame';frame.alt=$('frame').alt;frame.src=nextURL;
 try{await frame.decode();}catch(error){URL.revokeObjectURL(nextURL);if(ticket!==generation)return;throw error;}
 if(ticket!==generation){URL.revokeObjectURL(nextURL);return;}$('frame').replaceWith(frame);if(objectURL)URL.revokeObjectURL(objectURL);objectURL=nextURL;
 Object.assign(qa,{ready:true,region,view:view.id,sha256:digest});$('status').textContent='측정 기록과 그림 연결 확인 완료';
}
function selectRegion(requested){const rr=data.regions[$('region').value];$('view-select').replaceChildren(...rr.views.map(v=>new Option(v.name,v.id)));if(rr.views.some(v=>v.id===requested))$('view-select').value=requested;show().catch(fail);}
try{
 const response=await fetch(base+'response.json');if(!response.ok)throw Error('측정 기록 HTTP '+response.status);data=await response.json();if(data.schema!=='weight_response_v1')throw Error('측정 기록 형식 불일치');
 const params=new URLSearchParams(location.search);if(data.regions[params.get('region')])$('region').value=params.get('region');
 $('region').addEventListener('change',()=>selectRegion());$('view-select').addEventListener('change',()=>show().catch(fail));selectRegion(params.get('view'));
}catch(error){fail(error);}

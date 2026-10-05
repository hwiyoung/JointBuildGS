"use strict";
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=(x,n=4)=>typeof x==="number"&&Number.isFinite(x)?x.toFixed(n):"미측정";
const finite=x=>typeof x==="number"&&Number.isFinite(x);
const names={prior:"Prior · 기존 ALS",da3:"DA3 · 영상 depth",mvs:"MVS · 영상 depth"};
const strata={low_disagreement:"두 depth가 가까운 위치",high_disagreement:"두 depth 차이가 큰 위치",prior_hole:"Prior 결손 위치",mvs_hole:"MVS 결손 위치"};
const stateName=s=>({DEFINED_DESCRIPTIVE_ONLY:"점수 계산됨 · 신뢰 판정 전",PARTIAL_OR_UNDEFINED_SEE_SOURCE_STATUS:"일부 또는 전체 점수 미정의",UNDEFINED_INSUFFICIENT_COMMON_PIXELS:"공통 표본 부족",UNDEFINED_FLAT_PATCH:"밝기 변화 부족"}[s]||"자료 미지원");
const caseLabel=c=>{const id=c.case_id||"";const region=c.region||id.split("_")[0];const code=id.replace(/^[^_]+_/,"");return region+" · "+(strata[code]||c.label||id)};
let data,current,index=0,neighbor=0,step=1,loadToken=0;
const sourceKey=()=>$("#pair-select").value==="prior_mvs"?"mvs":"da3";
const asset=u=>u?"assets/diagnostic/"+String(u).replace(/^\.?\//,""):null;
function fig(url,title,kind="context"){
  if(!url)return '<figure><div class="empty">이 자료는 없습니다.<br>결손·미지원 상태를 수치 0으로 바꾸지 않습니다.</div><figcaption>'+esc(title)+'</figcaption></figure>';
  const path=asset(url);
  return '<figure class="'+kind+'"><button class="image-button" data-image="'+esc(path)+'" data-caption="'+esc(title)+'" aria-label="'+esc(title)+' 확대"><img src="'+esc(path)+'" alt="'+esc(title)+'"></button><figcaption>'+esc(title)+'</figcaption></figure>';
}
function metric(value,label){return '<div class="metric"><span class="value">'+esc(value)+'</span><span class="label">'+esc(label)+'</span></div>'}
function comp(n){return (n?.comparisons||{})[$("#pair-select").value]||{}}
function score(c,k){return c.scores?.[k]||{}}
function median(a){a=a.filter(finite).sort((x,y)=>x-y);if(!a.length)return null;const n=a.length;return n%2?a[(n-1)/2]:(a[n/2-1]+a[n/2])/2}
function getNeighbor(){return current?.neighbors?.[neighbor]||{}}
function sources(n){return n.sources||{}}
function pairStatus(c){return '<span class="status">'+esc(stateName(c.status))+' · 실제 가시성 미확인</span>'}
function selectionGuide(){
 const s=current.selection||{},count=Math.pow(current.exact_patch_size||9,2),reason=s.selection_reason;
 const rules={low_disagreement:'Prior와 DA3가 '+count+'픽셀 모두 유효하고, 픽셀별 절대 깊이 차이의 중앙값이 0.5m 이하',high_disagreement:'Prior와 DA3가 '+count+'픽셀 모두 유효하고, 픽셀별 절대 깊이 차이의 중앙값이 2m 이상',prior_hole:'Prior는 '+count+'픽셀 모두 결손이고 DA3는 모두 유효',mvs_hole:'Prior와 DA3는 '+count+'픽셀 모두 유효하고 MVS에는 하나 이상의 결손이 있음'};
 return '<div id="selection-guide" class="explain"><strong>이 위치를 고른 기준</strong><p>원사진 픽셀 (33, 33)부터 64픽셀 간격의 격자를 위에서 아래, 각 행에서는 왼쪽부터 검사해 다음 조건을 처음 만족한 위치입니다: '+esc(rules[reason]||'설정에 기록된 depth 조건')+'.</p><p>이 패치의 유효 depth: Prior '+esc(s.prior_count)+' / DA3 '+esc(s.da3_count)+' / MVS '+esc(s.mvs_count)+'개. Prior–DA3 절대 차이 중앙값: '+fmt(s.median_prior_da3_disagreement_m,4)+'m.</p><p>RGB 무늬·점수·GT·학습 결과로 고른 위치가 아닙니다. 지붕이나 변화 부위를 대표하도록 선정한 표본도 아닙니다. 흰 큰 테두리는 65×65 문맥, 분홍 작은 테두리는 점수를 계산한 9×9 영역입니다. 이 분류의 “두 depth”는 비교 선택에 관계없이 Prior와 DA3를 뜻합니다.</p></div>';
}
function supportCard(n,key){
 const s=n.sources?.[key]||{},p=s.center_projection_steps||{},camera=n.neighbor_camera_model||{},uv=p.projected_uv||[],z=p.neighbor_camera_xyz?.[2];
 const raw=s.raw_target_valid_count,usable=s.projectable_sample_count,total=Math.pow(current.exact_patch_size||9,2);
 const outside=uv.length===2&&uv.every(finite)&&(uv[0]<0||uv[0]>camera.width-1||uv[1]<0||uv[1]>camera.height-1);
 let why=raw===0?'원 depth가 모두 결손이어서 작은 패치의 투영 위치를 계산할 수 없습니다.':usable===0?'원 depth는 있지만, 이 이웃 사진에서 색을 가져올 수 있는 작은 패치 표본이 없습니다.':usable<total?'작은 패치 일부만 이 이웃 사진에서 색을 가져올 수 있습니다.':'작은 패치 전체가 이 이웃 사진에서 색을 가져올 수 있습니다.';
 if(outside)why+=' 중심 투영은 사진 범위 밖입니다.';
 else if(finite(z)&&z<=0)why+=' 중심은 이웃 카메라 뒤쪽입니다.';
 else if(raw>0&&!uv.every(finite))why+=' 패치 중심의 depth 또는 투영 좌표는 미지원입니다.';
 return '<div class="support-card" data-source="'+key+'"><strong>'+esc(names[key])+'</strong><p>원 depth '+esc(raw)+' / '+total+'개 → 이웃 RGB 조회 가능 '+esc(usable)+' / '+total+'개</p><p>'+esc(why)+'</p><p class="hint">중심 투영 (u, v) = ('+fmt(uv[0],1)+', '+fmt(uv[1],1)+'). 사진 범위 u: 0–'+esc(camera.width-1)+', v: 0–'+esc(camera.height-1)+'.</p></div>';
}
function readingGuide(){
 const k=sourceKey(),ns=current.neighbors||[],paired=ns.filter(n=>finite(score(comp(n),'prior').cost)&&finite(score(comp(n),k).cost));
 const p=paired.filter(n=>score(comp(n),'prior').cost<score(comp(n),k).cost).length,i=paired.filter(n=>score(comp(n),k).cost<score(comp(n),'prior').cost).length;
 let reading=paired.length?'같은 공통 픽셀에서 비용이 더 작은 쪽: Prior '+p+'장, '+k.toUpperCase()+' '+i+'장, 동률 '+(paired.length-p-i)+'장입니다. 이는 이 작은 패치의 밝기 패턴 비교 결과입니다.':'현재 비교쌍의 점수를 계산한 사진이 없어 두 후보의 적합도 우열을 말할 수 없습니다.';
 if(ns.length&&ns.every(n=>n.sources?.[k]?.raw_target_valid_count===0))reading+=' '+k.toUpperCase()+' 원 depth가 작은 패치에서 모두 결손입니다. Prior가 정답이라는 뜻은 아닙니다.';
 return '<div id="reading-guide" class="explain"><strong>이 위치의 관측 결과</strong><p>선정 이웃 '+ns.length+'장 중 이 비교쌍의 점수 계산 '+paired.length+'장. 이웃은 카메라 거리와 광축 조건으로 정했으며 이 패치가 사진에 들어오는지는 선정 조건에 없었습니다.</p><p>'+esc(reading)+'</p><p>나머지 사진은 반대표나 0점으로 합치지 않습니다. 아래 각 사진의 “패치 보기”에서 같은 물체·무늬를 비교하는지 확인해야 합니다. 가림과 무늬의 충분성, 패치 크기 민감도를 검증하기 전이므로 자동 가중치 결정으로 연결하지 않습니다.</p></div>';
}
function render(){
 if(!current)return;
 const n=getNeighbor(),src=sources(n),k=sourceKey(),c=comp(n),a=score(c,"prior"),b=score(c,k);
 const ref=current.ref_camera||current.reference_camera||"";
 const uv=current.center_uv||[];
 [...$("#neighbor-select").options].forEach((o,i)=>{const row=current.neighbors?.[i];if(row)o.textContent=(i+1)+'. '+row.camera_id+' · 공통 '+(comp(row).common_count??0)+'/'+Math.pow(current.exact_patch_size||9,2)+'픽셀'});
 $("#case-info").textContent=(current.region||"")+" · "+ref+" · 픽셀 ("+uv.join(", ")+") · "+(strata[current.selection?.selection_reason]||current.selection_reason||"고정 진단 위치");
 document.querySelectorAll(".steps button").forEach(el=>{const active=Number(el.dataset.step)===step;el.classList.toggle("active",active);if(active)el.setAttribute("aria-current","step");else el.removeAttribute("aria-current")});
 $("#prev").disabled=step===1;$("#next").disabled=step===6;$("#step-position").textContent=step+" / 6 단계";
 let body="";
 if(step===1){
  body='<h2>1. 같은 위치에서 두 깊이를 꺼냅니다</h2><p class="lead">원사진의 표시된 지점이 비교의 출발점입니다. 먼저 지붕·바닥·경계 중 어디인지 확인하세요.</p><div class="grid two">'+fig(current.ref_full_overlay_url,"기준 원사진 · 고정 패치 위치")+fig(current.ref_context_url,"위치를 이해하기 위한 큰 문맥 패치")+'</div>';
  const depths=current.depths||current.center_depths||{};
  body+='<div class="metrics">'+metric(fmt(depths.prior,3),"Prior camera-Z (m)")+metric(fmt(depths[k],3),(k==="mvs"?"MVS":"DA3")+" camera-Z (m)")+metric(String(current.exact_patch_size||9)+" × "+String(current.exact_patch_size||9),"실제 점수의 작은 패치")+'</div><div class="explain">깊이는 현재 카메라 축을 따른 값입니다. 두 숫자의 차이만으로 어느 source가 맞는지 결정하지 않습니다. 큰 문맥 그림 전체로 점수를 계산하지도 않습니다.</div>';
  body+=selectionGuide();
 }else if(step===2){
  body='<h2>2. 두 표면이 이웃 사진의 어디를 가리키는지 봅니다</h2><p class="lead">두 그림은 같은 이웃 사진입니다. 각 후보 depth로 계산한 투영 위치가 어디로 달라지는지 확인하세요.</p><div class="grid two">'+fig(src.prior?.full_overlay_url,"Prior가 예측한 위치 · "+(n.camera_id||""))+fig(src[k]?.full_overlay_url,names[k]+"가 예측한 위치 · "+(n.camera_id||""))+'</div><div class="explain">화면 안에 투영됐다는 사실은 그 표면이 실제로 보인다는 증명이 아닙니다. 다른 물체의 패치나 반복무늬를 가리키는지도 원사진에서 살펴보세요.</div>';
  body+='<div id="projection-support" class="grid two">'+supportCard(n,'prior')+supportCard(n,k)+'</div><p class="hint">테두리가 사진 밖에 있거나 경계 depth가 결손이면 표시가 없거나 끊길 수 있습니다. 큰 문맥의 테두리 유무와 작은 9×9 점수 표본 유무는 별개입니다. MVS 결손으로 Prior 표시를 함께 숨기지는 않습니다.</p>';
 }else if(step===3){
  body='<h2>3. 예측한 위치에서 패치를 가져옵니다</h2><p class="lead">세 그림의 픽셀 자리가 서로 대응합니다. 형태가 늘어나거나 꺾인 경우에도 후보의 기하를 그대로 보여줍니다.</p><h3>실제 점수에 사용하는 작은 패치 · 확대 표시</h3><div class="grid three">'+fig(current.ref_patch_url,"기준 사진의 원 패치","pixel")+fig(src.prior?.warped_patch_url,"Prior로 가져온 패치","pixel")+fig(src[k]?.warped_patch_url,names[k]+"로 가져온 패치","pixel")+'</div><h3>큰 문맥 · 위치 해석용, 점수에는 미포함</h3><div class="grid three">'+fig(current.ref_context_url,"기준 문맥")+fig(src.prior?.warped_context_url,"Prior로 가져온 문맥")+fig(src[k]?.warped_context_url,names[k]+"로 가져온 문맥")+'</div>';
  body+='<div id="patch-size-guide" class="explain"><strong>왜 9×9인가?</strong> 작은 국소 비교의 계산을 점검하기 위해 고정한 진단용 크기입니다. 최적 크기로 검증된 값이나 MVS 생성 설정을 그대로 가져온 값이 아닙니다. 실제 표본은 최대 81개이며 확대해도 표본이 늘지는 않습니다. 65×65는 위치 이해용입니다. 작은 패치는 무늬가 부족할 수 있고, 큰 패치는 다른 표면이나 가림 경계를 함께 포함할 수 있으므로 크기별 민감도 검증이 남아 있습니다.</div>';
 }else if(step===4){
  body='<h2>4. 두 후보를 같은 유효 표본으로 비교합니다</h2><p class="lead">Depth 결손이나 사진 밖 표본을 확인하고, 두 후보가 함께 비교 가능한 픽셀만 점수에 사용합니다.</p><div class="grid three">'+fig(src.prior?.valid_mask_url,"Prior의 유효 표본","pixel")+fig(src[k]?.valid_mask_url,names[k]+"의 유효 표본","pixel")+fig(c.common_valid_mask_url,"두 후보의 공통 유효 표본","pixel")+'</div><div class="metrics">'+metric(c.common_count??"미측정","공통 표본 수 / 최대 "+Math.pow(current.exact_patch_size||9,2))+'</div>'+pairStatus(c)+'<div class="explain">이 mask는 배열·투영의 계산 가능 범위입니다. 실제 가시성이나 정확성을 인증하지 않습니다. Prior↔DA3와 Prior↔MVS의 공통 mask는 따로 계산합니다.</div>';
  body+='<div id="mask-legend" class="explain"><span class="swatch white"></span> 흰색 = 1, 계산 가능한 픽셀. <span class="swatch black"></span> 검은색 = 0, 결손·사진 밖 등으로 계산 불가.<p>모두 흰색이면 9×9의 81픽셀 모두 사용할 수 있다는 뜻입니다. “오차 0”이나 “정답”의 색이 아닙니다. 이 그림은 사진이 아니라 예/아니오를 그린 mask입니다. 패치 사진과 잔차 그림의 회색은 미지원 표시입니다.</p></div>';
 }else if(step===5){
  body='<h2>5. 밝기 차이를 정규화한 뒤 패턴을 비교합니다</h2><p class="lead">각 패치의 공통 표본에서 평균을 빼고 표준편차로 나눕니다. 밝고 어두운 부분의 배치가 같은지 확인하세요.</p><div class="grid three">'+fig(c.standardized_reference_url,"정규화한 기준 패치 · 동일 표시 범위","pixel")+fig(c.standardized_source_urls?.prior,"정규화한 Prior 패치","pixel")+fig(c.standardized_source_urls?.[k],"정규화한 "+names[k]+" 패치","pixel")+'</div><h3>정규화 후 차이 · 공통 표본</h3><p class="hint">빨강은 정규화한 기준 밝기가 더 큼, 파랑은 투영 쪽이 더 큼, 가운데 옅은색은 차이 0에 가까움입니다. 회색은 미지원입니다. 표시 범위는 −3~3으로 고정합니다.</p><div class="grid two">'+fig(c.normalized_residual_urls?.prior,"기준 ↔ Prior의 정규화 잔차","pixel")+fig(c.normalized_residual_urls?.[k],"기준 ↔ "+names[k]+"의 정규화 잔차","pixel")+'</div><div class="table-wrap"><table><thead><tr><th>패치</th><th>기준 표준편차</th><th>투영 패치 표준편차</th></tr></thead><tbody><tr><td>Prior</td><td>'+fmt(a.std_reference)+'</td><td>'+fmt(a.std_warp)+'</td></tr><tr><td>'+names[k]+'</td><td>'+fmt(b.std_reference)+'</td><td>'+fmt(b.std_warp)+'</td></tr></tbody></table></div><p class="hint">원영상 grayscale은 [0,1]. 정규화 그림의 표시 clip은 수치 점수에 적용하지 않습니다. 무텍스처에서는 정규화·NCC가 정의되지 않을 수 있습니다.</p>';
 }else{
  const cs=(current.neighbors||[]).map(comp),paired=cs.filter(x=>finite(score(x,"prior").cost)&&finite(score(x,k).cost)),as=paired.map(x=>score(x,"prior").cost),bs=paired.map(x=>score(x,k).cost),ds=paired.map(x=>score(x,"prior").cost-score(x,k).cost);
  body='<h2>6. 사진별 점수를 함께 읽습니다</h2><p class="lead">ZNCC는 높을수록, 비용 (1−ZNCC)/2는 낮을수록 패턴이 비슷합니다. 작은 비용만으로 실제 기하나 가중치의 승자를 확정하지 않습니다.</p><div class="metrics">'+metric(fmt(median(as)),"Prior 비용 중앙값")+metric(fmt(median(bs)),(k==="mvs"?"MVS":"DA3")+" 비용 중앙값")+metric(fmt(median(ds)),"대응 비용차 중앙값: Prior − Image")+'</div><div class="table-wrap"><table id="score-table"><thead><tr><th>이웃 사진</th><th>공통 표본</th><th>Prior ZNCC</th><th>'+esc(k.toUpperCase())+' ZNCC</th><th>Prior 비용</th><th>'+esc(k.toUpperCase())+' 비용</th><th>계산 상태</th><th></th></tr></thead><tbody>';
  (current.neighbors||[]).forEach((row,ri)=>{const x=comp(row),p=score(x,"prior"),i=score(x,k);body+='<tr class="'+(ri===neighbor?"selected":"")+'"><td class="camera">'+esc(row.camera_id)+'</td><td class="num">'+esc(x.common_count??"—")+'</td><td class="num">'+fmt(p.zncc)+'</td><td class="num">'+fmt(i.zncc)+'</td><td class="num">'+fmt(p.cost)+'</td><td class="num">'+fmt(i.cost)+'</td><td>'+esc(stateName(x.status))+'</td><td><button class="table-btn" data-view="'+ri+'">패치 보기</button></td></tr>'});
  body+='</tbody></table></div><div class="explain">양의 비용차는 이 비교에서 Image의 비용이 작다는 뜻입니다. <strong>현재 source 선택·q 계산은 하지 않습니다.</strong> 같은 생성 사진을 이용한 내부 적합도이고 가시성·신뢰 문턱도 검증 전입니다. 결손/미정의 값은 평균에서 0으로 계산하지 않습니다.</div><p class="hint">중앙값은 두 source의 비용이 모두 정의된 같은 이웃 집합에서 계산합니다. 각 비용 중앙값의 차이와 대응 비용차의 중앙값은 일반적으로 다릅니다. 서로 다른 공통 mask로 계산한 두 source 쌍의 중앙값을 직접 순위화하지 마세요.</p>';
  body+=readingGuide();
 }
 $("#step-body").innerHTML=body;bindImages();
 document.querySelectorAll("[data-view]").forEach(el=>el.addEventListener("click",()=>{neighbor=Number(el.dataset.view);$("#neighbor-select").value=String(neighbor);step=3;render()}));
 window.__walkthrough={caseId:current.case_id,step,neighbor,pair:$("#pair-select").value,caseCount:data.cases.length,neighborCount:current.neighbors?.length||0};
}
function bindImages(){document.querySelectorAll("[data-image]").forEach(el=>el.addEventListener("click",()=>{$("#zoom-image").src=el.dataset.image;$("#zoom-image").alt=el.dataset.caption;$("#zoom-caption").textContent=el.dataset.caption;$("#zoom").showModal()}))}
async function loadCase(i){
 const token=++loadToken;index=i;const entry=data.cases[i];if(!entry)throw Error("위치 목록이 비어 있습니다");
 const path=entry.path||entry.case_json||entry.case_url;
 const response=await fetch(asset(path));if(!response.ok)throw Error("위치 자료를 읽지 못했습니다: "+response.status);
 const item=await response.json();if(token!==loadToken)return;current=item;
 const pairedIndex=(current.neighbors||[]).findIndex(n=>Number(comp(n).common_count)>=2);
 const visibleIndex=(current.neighbors||[]).findIndex(n=>Number(n.sources?.prior?.projectable_sample_count)>0||Number(n.sources?.[sourceKey()]?.projectable_sample_count)>0);
 neighbor=pairedIndex>=0?pairedIndex:Math.max(0,visibleIndex);
 $("#neighbor-select").replaceChildren(...(current.neighbors||[]).map((n,i)=>{const o=document.createElement("option");o.value=String(i);o.textContent=(i+1)+". "+n.camera_id;return o}));
 $("#neighbor-select").value=String(neighbor);$("#case-link").href=asset(path);render();
}
function fail(e){$("#step-body").innerHTML='<div class="error">자료를 표시하지 못했습니다: '+esc(e.message)+'</div>';window.__walkthroughError=String(e)}
$("#case-select").addEventListener("change",e=>loadCase(Number(e.target.value)).catch(fail));
$("#pair-select").addEventListener("change",render);
$("#neighbor-select").addEventListener("change",e=>{neighbor=Number(e.target.value);render()});
document.querySelectorAll("[data-step]").forEach(el=>el.addEventListener("click",()=>{step=Number(el.dataset.step);render()}));
$("#prev").addEventListener("click",()=>{step=Math.max(1,step-1);render()});
$("#next").addEventListener("click",()=>{step=Math.min(6,step+1);render()});
$("#close-zoom").addEventListener("click",()=>$("#zoom").close());
(async()=>{const r=await fetch("data.json");if(!r.ok)throw Error("자료 목록 HTTP "+r.status);data=await r.json();$("#case-select").replaceChildren(...data.cases.map((c,i)=>{const o=document.createElement("option");o.value=String(i);o.textContent=caseLabel(c);return o}));const first=Math.max(0,data.cases.findIndex(c=>c.case_id==="P2_low_disagreement"));$("#case-select").value=String(first);await loadCase(first)})().catch(fail);

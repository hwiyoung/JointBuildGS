const $ = id => document.getElementById(id);
const qa = window.__GEOGS_RGB_DIAGNOSTIC_QA__ = {ready:false,errors:[]};
let manifest, manifestURL, selected, generation=0;
const fmt = (value,digits=2) => Number.isFinite(value) ? value.toFixed(digits) : '—';
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
function dataURL(relative){const url=new URL(relative,manifestURL);if(url.origin!==location.origin||!url.pathname.startsWith('/data/rgb_diagnostic_v1/'))throw Error('비교 자료 경로가 허용 범위를 벗어났습니다.');return url.href;}
function fail(error){qa.errors.push(String(error));$('error').hidden=false;$('error').textContent=String(error);$('status').textContent='비교 자료를 확인하지 못했습니다.';}
function openDetail(condition){
  $('detail-title').textContent=`${selected.region} · ${selected.split==='train'?'학습뷰':'평가뷰'} · ${selected.name}`;
  $('detail-method').textContent=`${condition.label} · prior ${condition.prior}`;
  $('detail-photo').src=dataURL(selected.photo_url);$('detail-render').src=dataURL(condition.render_url);
  $('zoom').value='1';resizeDetail();$('detail').showModal();
  document.querySelectorAll('.viewport').forEach(el=>{el.scrollTop=0;el.scrollLeft=0;});
}
function resizeDetail(){const scale=Number($('zoom').value);for(const id of ['detail-photo','detail-render']){const img=$(id);img.style.width=`${selected.width*scale}px`;img.style.height=`${selected.height*scale}px`;}}
function card(condition,loads){
  const {width,height}=selected;
  const photo=!condition,article=node('article',undefined,'card'),head=node('div',undefined,'card-head');
  head.append(node('h3',photo?'원사진':condition.label));
  head.append(node('div',photo?'고정 영역 · 원본 픽셀':`ROI PSNR ${fmt(condition.psnr_roi_db)} dB · SSIM ${fmt(condition.ssim_roi,3)}`,'metrics'));
  const wrap=node('div',undefined,'image-wrap'),img=new Image();
  img.alt=photo?`${selected.name} 원사진`:`${condition.label}, prior ${condition.prior}, ${selected.name}`;
  img.src=dataURL(photo?selected.photo_url:condition.render_url);img.dataset.condition=photo?'photo':condition.id;
  loads.push(img.decode().then(()=>{if(img.naturalWidth!==width||img.naturalHeight!==height)throw Error('원사진과 렌더의 crop 크기가 다릅니다.');}));
  wrap.append(img);const foot=node('div',undefined,'card-foot');
  if(photo)foot.append(node('span',`${selected.width} × ${selected.height} px`));
  else{foot.append(node('span','full-SH RGB'));const button=node('button','1:1 크게 비교');button.type='button';button.addEventListener('click',()=>openDetail(condition));foot.append(button);}
  const full=photo?selected.photo_full_url:condition.render_full_url;
  if(full){const link=node('a','전체 영상 ↗');link.href=dataURL(full);link.target='_blank';link.rel='noopener';foot.append(link);}
  article.append(head,wrap,foot);return article;
}
async function render(){
  const token=++generation;qa.ready=false;
  selected=manifest.cases.find(row=>row.id===$('case').value);if(!selected)throw Error('선택한 사진이 없습니다.');
  $('case-meta').textContent=`${selected.name} · 카메라/사진 인덱스 ${selected.index} · 원본 crop [${selected.bbox.join(', ')}] · ${selected.width} × ${selected.height} px`;
  const fragment=document.createDocumentFragment(),loads=[],prior=$('prior').value;
  for(const weight of [0.005,0.0005]){
    if(prior!=='both'&&Number(prior)!==weight)continue;
    const section=node('section',undefined,'weight-row'),title=node('div',undefined,'weight-title');title.append(node('h2',`Prior ${weight}`),node('span','보호 유지 · 같은 사진과 crop'));
    const cards=node('div',undefined,'cards');cards.style.setProperty('--image-ratio',`${selected.width}/${selected.height}`);cards.append(card(null,loads));
    const conditions=selected.conditions.filter(c=>Number(c.prior)===weight);
    if(conditions.length!==3)throw Error('세 감독 조건이 모두 있어야 비교할 수 있습니다.');
    for(const mode of ['da3','mvs','mvs_pgsr']){const condition=conditions.find(c=>c.mode===mode);if(!condition)throw Error(`누락 조건: ${mode}`);cards.append(card(condition,loads));}
    section.append(title,cards);fragment.append(section);
  }
  $('comparisons').replaceChildren(fragment);await Promise.all(loads);if(token!==generation)return;
  Object.assign(qa,{ready:true,case_id:selected.id,region:selected.region,split:selected.split,prior,images:loads.length,case_count:manifest.cases.length});
  const address=new URL(location.href);address.searchParams.set('region',selected.region);address.searchParams.set('split',selected.split);address.searchParams.set('case',selected.id);address.searchParams.set('prior',prior);history.replaceState(null,'',address);
  $('status').textContent=`${selected.region} · ${selected.split==='train'?'학습뷰':'평가뷰'} · 원사진과 렌더 ${loads.length}개 표시 완료. 작은 무늬는 ‘1:1 크게 비교’에서 확인하세요.`;
}
function selectCases(){const previous=$('case').value||new URLSearchParams(location.search).get('case'),rows=manifest.cases.filter(c=>c.region===$('region').value&&c.split===$('split').value);$('case').replaceChildren(...rows.map((row,i)=>{const option=node('option',`사진 ${i+1} · ${row.name}`);option.value=row.id;return option;}));if(rows.some(row=>row.id===previous))$('case').value=previous;render().catch(fail);}
try{
  const pointerResponse=await fetch('/data/rgb_diagnostic_v1/latest.json',{cache:'no-store'});if(!pointerResponse.ok)throw Error('학습뷰·평가뷰 진단 자료를 준비 중입니다.');
  const pointer=await pointerResponse.json();manifestURL=new URL(pointer.manifest_url,location.href);dataURL(manifestURL.href);
  const response=await fetch(manifestURL,{cache:'no-store'});if(!response.ok)throw Error('비교 manifest를 읽을 수 없습니다.');manifest=await response.json();
  if(manifest.status!=='PASS'||manifest.scientific_verdict!==null||manifest.cases.length!==12)throw Error('완료된 12개 사진 비교 자료가 필요합니다.');
  qa.manifest_url=manifestURL.href;$('manifest').href=manifestURL.href;
  const query=new URLSearchParams(location.search);for(const id of ['region','split','prior']){const value=query.get(id);if([...$(id).options].some(option=>option.value===value))$(id).value=value;}
  for(const id of ['region','split'])$(id).addEventListener('change',selectCases);
  for(const id of ['case','prior'])$(id).addEventListener('change',()=>render().catch(fail));
  $('close-detail').addEventListener('click',()=>$('detail').close());$('zoom').addEventListener('change',resizeDetail);
  const viewports=[...document.querySelectorAll('.viewport')];for(const viewport of viewports)viewport.addEventListener('scroll',()=>{const other=viewports.find(v=>v!==viewport);if(other.scrollLeft!==viewport.scrollLeft)other.scrollLeft=viewport.scrollLeft;if(other.scrollTop!==viewport.scrollTop)other.scrollTop=viewport.scrollTop;});
  selectCases();
}catch(error){fail(error);}

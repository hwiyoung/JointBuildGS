/* Display-only recounts. Original arrays are never written. */
'use strict';
window.U11=(()=>{
const C=DV.M.view_v1_1, finite=Number.isFinite;
function roofType(d,z,i){return DV.at(z.roof_type,i)||d.faces?.items[d.faces.assignment[i]]?.roof_type||''}
function allowed(d,z,i,f){
  const m='mvs_'+f.v;
  if(f.scope==='eval'&&!z.in_eval[i])return false;
  if(f.cell!=='all'&&z.cell[i]!==Number(f.cell))return false;
  if(f.shape==='roof'&&!z.roof_like[i]||f.shape==='wall'&&z.roof_like[i])return false;
  if(f.roof!=='all'&&roofType(d,z,i)!==f.roof)return false;
  if(f.status!=='all'&&z[m+'_status'][i]!==Number(f.status))return false;
  if(f.flag==='one'&&!(z[m+'_status'][i]===0&&z[m+'_quadrants'][i]<3))return false;
  if(f.flag==='weak'&&!(z[m+'_status'][i]===0&&z[m+'_support_lmeds'][i]<.5))return false;
  if(f.flag==='thinned'&&!(z[m+'_thinned_inner'][i]===1||z[m+'_thinned_ring'][i]===1))return false;
  if(f.flag==='missed'&&!(z[m+'_status'][i]===0&&finite(z[m+'_e'][i])&&z[m+'_e'][i]>.2&&z[m+'_e'][i]>2*z[m+'_u'][i]))return false;
  if(f.range){const l=DV.M.config.layers.find(x=>x.id===f.left),v=DV.value(d,z,l,f.v,i);if(!finite(v)||v<f.range[0]||v>f.range[1])return false}
  return true;
}
function observations(datasets,filters,pooled,exclude){
  const out={mvs:[],prior:[]},corr=DV.M.cells.indexOf(C.population.exclusion_cell);
  datasets.forEach((d,si)=>{const z=DV.rows(d,pooled?C.population.pool_radii[d.meta.site]:filters.r),m='mvs_'+filters.v;
    for(let i=0;i<d.n;i++){
      if(!allowed(d,z,i,filters))continue;
      const base={i,site:d.meta.site,case:d.meta.id,si,roof:!!z.roof_like[i],rt:roofType(d,z,i)};
      const u=z[m+'_u'][i],e=z[m+'_e'][i];
      if(z[m+'_status'][i]===0&&finite(u)&&finite(e))out.mvs.push({...base,u:u*100,e:e*100});
      if(exclude&&z.cell[i]===corr)continue;
      const pu=z.u_prior[i],pe=d.meta.prior==='ALS'?z.als_e[i]:z.eL[i];
      if((d.meta.prior!=='ALS'||z.als_status[i]===0)&&finite(pu)&&finite(pe))out.prior.push({...base,u:pu*100,e:pe*100});
    }
  });return out;
}
function row(points,label,select,source){
  const u=US.dist(points.map(p=>p.u)),e=US.dist(points.map(p=>p.e));
  return {source,label,select,n:points.length,u_median_cm:u.p50,e_median_cm:e.p50,e_p25_cm:e.p25,e_p75_cm:e.p75,
    median_e_over_u:US.q(points.map(p=>p.u>0?p.e/p.u:NaN),.5),draw:points.length>=C.calibration.min_patches};
}
function calibration(points,source,lod2,pooled,detail){
  if(!lod2){const edges=C.calibration.bins_cm;return edges.slice(0,-1).map((lo,j)=>{const hi=edges[j+1];return row(points.filter(p=>p.u>=lo&&(hi===null||p.u<hi)),hi===null?'40 초과':lo+'~'+hi,{kind:'bin',lo,hi,source},source)})}
  const groups=new Map();for(const p of points){const group=(!p.roof?'벽':(!pooled||detail)?'지붕 '+(p.rt||'형태 없음'):'지붕'),key=(pooled?p.site+' · ':'')+group;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(p)}
  return [...groups].sort(([a],[b])=>a.localeCompare(b)).map(([label,ps])=>row(ps,label,{kind:'group',source,site:pooled?ps[0].site:null,roof:ps[0].roof,rt:ps[0].roof&&(!pooled||detail)?ps[0].rt:null},source));
}
function sparse(points,constant=false){
  if(constant)return {available:false,reason:'LoD2 불확실도는 20 cm 한 값이므로 줄 세울 순서가 없습니다.',n:points.length};
  const n=points.length,base=n?points.reduce((s,p)=>s+p.e,0)/n:null;
  if(!n||!(base>0))return {available:false,reason:!n?'값과 실제 오차가 함께 있는 패치가 없습니다.':'처음 실제 오차 평균이 0이어서 나눌 수 없습니다.',n,base_mean_cm:base};
  const suffix=key=>{const a=points.slice().sort((a,b)=>b[key]-a[key]||a.i-b.i||a.si-b.si),sum=new Float64Array(n+1);for(let j=n-1;j>=0;j--)sum[j]=sum[j+1]+a[j].e;return sum};
  const u=suffix('u'),e=suffix('e');const rows=C.sparsification.remove_percent.map(percent=>{const k=Math.floor(n*percent/100),count=n-k;return {percent,removed:k,remaining:count,mean_cm:u[k]/count,ideal_mean_cm:e[k]/count,curve:u[k]/count/base,ideal:e[k]/count/base,random:1}});
  let area=0,random=0;for(let j=1;j<rows.length;j++){const a=rows[j-1],b=rows[j],dx=(b.percent-a.percent)/100;area+=dx*((a.curve-a.ideal)+(b.curve-b.ideal))/2;random+=dx*((1-a.ideal)+(1-b.ideal))/2}
  return {available:true,n,base_mean_cm:base,rows,area_curve_ideal:area,area_random_ideal:random};
}
function calculate(datasets,filters,pooled=false,exclude=false,detail=false){
  const o=observations(datasets,filters,pooled,exclude),lod2=datasets[0].meta.prior==='LoD2';
  return {prior:datasets[0].meta.prior,pooled,exclude,detail,filters,
    calibration:[...calibration(o.mvs,'mvs',false,pooled,detail),...calibration(o.prior,'prior',lod2,pooled,detail)],
    sparse:{mvs:sparse(o.mvs),prior:sparse(o.prior,lod2)},counts:{mvs:o.mvs.length,prior:o.prior.length}};
}
function selected(p,d,z,i,v,exclude){const source=p.source,m=source==='mvs'?'mvs_'+v:d.meta.prior==='ALS'?'als':null;
  if(source==='prior'&&exclude&&z.cell[i]===DV.M.cells.indexOf(C.population.exclusion_cell))return false;
  const u=(source==='prior'?z.u_prior[i]:z[m+'_u'][i])*100,e=source==='prior'&&d.meta.prior==='LoD2'?z.eL[i]:z[m+'_e'][i];
  if(m&&z[m+'_status'][i]!==0||!finite(u)||!finite(e))return false;
  if(p.kind==='bin')return u>=p.lo&&(p.hi===null||u<p.hi);
  return (!p.site||p.site===d.meta.site)&&!!z.roof_like[i]===p.roof&&(p.rt===null||p.rt===roofType(d,z,i));
}
function aggregate(d,z,ids,layer,v){
  const values=[];let validArea=0,missedArea=0;const counts=new Map();
  for(const i of ids){const x=DV.value(d,z,layer,v,i);if(typeof x!=='string'&&!finite(x))continue;values.push(x);validArea+=z.area[i];if(layer.id==='missed'&&x===1)missedArea+=z.area[i];counts.set(x,(counts.get(x)||0)+1)}
  const n=values.length,frac=ids.length?n/ids.length:0,insufficient=n<C.faces.insufficient.min_valid||frac<C.faces.insufficient.min_valid_fraction;
  const s={n,total:ids.length,valid_fraction:frac,insufficient,area_m2:ids.reduce((sum,i)=>sum+z.area[i],0),p25:null,p50:null,p75:null,value:null,majority_share:null};
  if(layer.id==='missed'){s.value=validArea?100*missedArea/validArea:null;s.p50=s.value;return s}
  if(layer.kind==='category'){const a=[...counts].sort((a,b)=>b[1]-a[1]||String(a[0]).localeCompare(String(b[0])));s.value=a[0]?.[0]??null;s.majority_share=n?(a[0]?.[1]||0)/n:null;return s}
  const st=US.dist(values);return {...s,value:st.p50,p25:st.p25,p50:st.p50,p75:st.p75};
}
function faceValues(d,z,mask,left,right,v){
  const members=Array.from({length:d.faces.items.length},()=>[]);for(let i=0;i<d.n;i++)if(mask[i])members[d.faces.assignment[i]].push(i);
  return d.faces.items.map((face,index)=>({face,index,ids:members[index],left:aggregate(d,z,members[index],left,v),right:aggregate(d,z,members[index],right,v)})).filter(f=>f.ids.length);
}
function pairStats(faces){const rows=faces.filter(f=>!f.face.grid&&!f.left.insufficient&&!f.right.insufficient&&finite(f.left.value)&&finite(f.right.value)),left=rows.map(f=>f.left.value),right=rows.map(f=>f.right.value);return {n:rows.length,rho:US.rho(left,right),median_right_over_left:US.q(rows.map(f=>f.left.value>0?f.right.value/f.left.value:NaN),.5)}}
return {C,allowed,roofType,observations,calibration,sparse,calculate,selected,aggregate,faceValues,pairStats};
})();

(() => {
  let data;
  const select=document.getElementById('evidence-case'),canvas=document.getElementById('evidence-plot');
  function draw() {
    const item=data.cases[Number(select.value)]; if(!item)return;
    const ctx=canvas.getContext('2d'),W=canvas.width,H=canvas.height,pad=35;
    ctx.fillStyle='#121b25';ctx.fillRect(0,0,W,H);
    const x=v=>pad+(v-data.offsets[0])/(data.offsets.at(-1)-data.offsets[0])*(W-2*pad);
    const y=v=>H-pad-v*(H-2*pad);
    for(const [bounds,color] of [[item.observation,'#ffffff20'],[item.allowed,'#4adba63a']]) {
      ctx.fillStyle=color;ctx.fillRect(x(bounds[0]),pad,x(bounds[1])-x(bounds[0]),H-2*pad);
    }
    ctx.strokeStyle='#789';ctx.beginPath();ctx.moveTo(pad,pad);ctx.lineTo(pad,H-pad);ctx.lineTo(W-pad,H-pad);ctx.stroke();
    ctx.fillStyle='#dde7ef';ctx.font='12px sans-serif';
    for(const v of data.offsets)ctx.fillText(v.toFixed(2),x(v)-12,H-10);
    for(const [i,values] of item.cost.entries()) {
      ctx.strokeStyle=i?'#f3a757':'#64b5ff';ctx.lineWidth=2;ctx.beginPath();
      values.forEach((v,j)=>j?ctx.lineTo(x(data.offsets[j]),y(v)):ctx.moveTo(x(data.offsets[j]),y(v)));ctx.stroke();
    }
    for(const [v,color] of [[0,'#eeeeee'],[item.final_offset,'#47ecae']]) {
      ctx.strokeStyle=color;ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(x(v),pad);ctx.lineTo(x(v),H-pad);ctx.stroke();ctx.setLineDash([]);
    }
    document.getElementById('evidence-numbers').textContent=`초기 기준 0m · 관측 [${item.observation.map(v=>v.toFixed(3)).join(', ')}]m → 허용 [${item.allowed.map(v=>v.toFixed(3)).join(', ')}]m · 최종 ${item.final_offset.toFixed(4)}m · ${item.conditional_eligible?'조건부 위치 구간 통과':'미해결: 조건부 채택 아님'} · ε=${data.epsilon_m}m (개발 설정)`;
  }
  fetch('evidence.json').then(r=>r.json()).then(value=>{
    data=value;window.p2Evidence=data;
    document.getElementById('evidence-summary').textContent=data.summary;
    data.cases.forEach((item,i)=>select.add(new Option(`원본 seed ${item.seed_id} · ${item.initial_eligible?'초기 사용 범위 안':'보정 필요'} · x=${item.xyz[0].toFixed(1)}, y=${item.xyz[1].toFixed(1)}`,String(i))));
    select.addEventListener('change',draw);draw();
    document.getElementById('evidence-locate').addEventListener('click',async()=>{
      const item=data.cases[Number(select.value)];
      if(!item?.projection)return;
      p2Viewer.setMode('grid');
      await p2Viewer.setView(item.projection.image_id);p2Viewer.zoomTo(2);
      p2ViewerState.center={x:item.projection.u,y:item.projection.v};p2Viewer.redraw();
      document.getElementById('grid-mode').scrollIntoView({behavior:'smooth',block:'start'});
    });
    const table=document.createElement('table');table.style.width='100%';
    const head=table.createTHead().insertRow();['조건','MAE ↓','PSNR ↑','최종 1mm 초과 갱신','미해결 관측점','보호 ray 위반','UAS 거리 p90 ↓'].forEach(t=>{const c=document.createElement('th');c.textContent=t;head.append(c);});
    const body=table.createTBody();data.results.forEach(row=>{const r=body.insertRow();[row.label,row.mae.toFixed(5),row.psnr_db.toFixed(2)+'dB',row.changed,row.unresolved,row.violations,row.p90_m===null?'미평가':row.p90_m.toFixed(4)+'m'].forEach(t=>{r.insertCell().textContent=t;});});
    document.getElementById('result-table').append(table);
  }).catch(error=>document.getElementById('evidence-summary').textContent=error.message);
})();

/* PHD-MAIN-FLOATDIAG-v1 offline GLB viewer. No external libraries or requests. */
(() => {
  'use strict';
  const D=window.FLOATDIAG_DATA, assets=window.FLOATDIAG_GLB;
  function decode(s){const b=atob(s),a=new Uint8Array(b.length);for(let i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return a.buffer;}
  function model(buffer){
    const dv=new DataView(buffer);if(dv.getUint32(0,true)!==0x46546c67)throw Error('GLB header');
    const jl=dv.getUint32(12,true),doc=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,jl)));
    const bin=20+jl+8,p=doc.meshes[0].primitives[0];
    function arr(i){const a=doc.accessors[i],v=doc.bufferViews[a.bufferView],start=bin+(v.byteOffset||0)+(a.byteOffset||0);
      const n=a.count*({VEC3:3,VEC4:4,SCALAR:1}[a.type]),T={5126:Float32Array,5125:Uint32Array,5121:Uint8Array}[a.componentType];
      return new T(buffer,start,n);}
    return {positions:arr(p.attributes.POSITION),colours:arr(p.attributes.COLOR_0),indices:arr(p.indices)};
  }
  function viewer(caseInfo, host){
    const select=document.createElement('select'),palette=document.createElement('select');
    for(const r of D.results){const o=new Option(r.label,r.id);select.add(o);}
    palette.add(new Option('뜬 면 색','float'));palette.add(new Option('원래 색','colour'));
    const reset=document.createElement('button');reset.textContent='처음 각도';
    const controls=document.createElement('div');controls.className='viewer-controls';controls.append(select,palette,reset);host.append(controls);
    const canvas=document.createElement('canvas');canvas.width=900;canvas.height=600;canvas.tabIndex=0;
    canvas.setAttribute('aria-label',caseInfo.id+' 실제 결과 메시. 드래그 또는 방향키로 회전, 휠 또는 더하기 빼기로 확대.');host.append(canvas);
    const status=document.createElement('p');status.className='viewer-status';host.append(status);
    const gl=canvas.getContext('webgl2',{antialias:true,preserveDrawingBuffer:true});
    if(!gl){status.textContent='이 환경에서는 3차원 표시를 사용할 수 없습니다. 아래 캡처와 GLB 파일을 확인하세요.';return;}
    const vs=`#version 300 es
    in vec3 position;in vec4 colour;uniform vec3 eye,right,up,forward;uniform float aspect;
    out vec4 col;out vec3 world;
    void main(){vec3 p=position-eye;float z=dot(p,forward);float f=2.41421356237;
      gl_Position=vec4(f*dot(p,right),f*aspect*dot(p,up),z*1.00002-.0200002,z);col=colour;world=position;}`;
    const fs=`#version 300 es
    precision highp float;in vec4 col;in vec3 world;out vec4 pixel;
    void main(){vec3 n=normalize(cross(dFdx(world),dFdy(world)));float l=.65+.35*abs(dot(n,normalize(vec3(.3,-.4,.85))));pixel=vec4(col.rgb*l,1.);}`;
    function shader(type,s){const x=gl.createShader(type);gl.shaderSource(x,s);gl.compileShader(x);if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(x));return x;}
    const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vs));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.useProgram(program);
    const locations={};for(const k of ['eye','right','up','forward','aspect'])locations[k]=gl.getUniformLocation(program,k);
    let az=Math.PI/4,el=Math.PI/18,distance=2.5*caseInfo.radius,count=0,buffers=[];
    function draw(){
      const dir=[Math.cos(el)*Math.cos(az),Math.cos(el)*Math.sin(az),Math.sin(el)],right=[-Math.sin(az),Math.cos(az),0];
      const up=[-Math.sin(el)*Math.cos(az),-Math.sin(el)*Math.sin(az),Math.cos(el)];
      gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(.973,.973,.973,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
      gl.uniform3fv(locations.eye,dir.map(x=>x*distance));gl.uniform3fv(locations.right,right);gl.uniform3fv(locations.up,up);gl.uniform3fv(locations.forward,dir.map(x=>-x));
      gl.uniform1f(locations.aspect,canvas.width/canvas.height);gl.drawElements(gl.TRIANGLES,count,gl.UNSIGNED_INT,0);
      canvas.dataset.rendered=String(count>0);
      canvas.dataset.camera=JSON.stringify([az,el,distance]);canvas.dataset.glError=String(gl.getError());
    }
    function load(){
      const key=caseInfo.id+'__'+select.value+'__'+palette.value+'.glb';
      if(!assets[key]){status.textContent='확인 불가: '+key;return;}
      const m=model(decode(assets[key]));for(const b of buffers)gl.deleteBuffer(b);buffers=[];
      for(const [name,data,size,type,norm] of [['position',m.positions,3,gl.FLOAT,false],['colour',m.colours,4,gl.UNSIGNED_BYTE,true]]){
        const b=gl.createBuffer();buffers.push(b);gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
        const a=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,size,type,norm,0,0);
      }
      const b=gl.createBuffer();buffers.push(b);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,m.indices,gl.STATIC_DRAW);count=m.indices.length;
      status.textContent='면 '+(count/3).toLocaleString()+'개 · 결과를 바꿔도 각도 유지 · 드래그 회전 / 휠 확대';draw();
      canvas.dataset.model=key;canvas.dataset.faces=String(count/3);
    }
    let last=null;canvas.addEventListener('pointerdown',e=>{last=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
    canvas.addEventListener('pointerup',()=>last=null);canvas.addEventListener('pointermove',e=>{if(!last)return;az-=(e.clientX-last[0])*.008;el=Math.max(-1.4,Math.min(1.55,el+(e.clientY-last[1])*.008));last=[e.clientX,e.clientY];draw();});
    canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(caseInfo.radius*.3,Math.min(caseInfo.radius*12,distance*Math.exp(e.deltaY*.001)));draw();},{passive:false});
    canvas.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-'].includes(e.key))return;e.preventDefault();if(e.key==='ArrowLeft')az-=.1;if(e.key==='ArrowRight')az+=.1;if(e.key==='ArrowUp')el=Math.min(1.55,el+.1);if(e.key==='ArrowDown')el=Math.max(-1.4,el-.1);if(e.key==='+')distance*=.9;if(e.key==='-')distance*=1.1;draw();});
    select.addEventListener('change',load);palette.addEventListener('change',load);reset.addEventListener('click',()=>{az=Math.PI/4;el=Math.PI/18;distance=2.5*caseInfo.radius;draw();});
    load();
  }
  for(const c of D.cases){const host=document.querySelector('[data-viewer="'+c.id+'"]');if(host)viewer(c,host);}
})();

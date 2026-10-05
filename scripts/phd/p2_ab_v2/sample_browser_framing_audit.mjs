// UI projection audit only. Node built-ins; no project dependency or GT input.
// Usage: node sample_browser_framing_audit.mjs BROWSER_QA_JSON FRESH_REPORT_JSON
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import path from 'node:path';

const [qaPath,output]=process.argv.slice(2);
if(!qaPath||!output)throw Error('BROWSER_QA_JSON and fresh report path required');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const qaBytes=await fs.readFile(qaPath),qa=JSON.parse(qaBytes.toString());
if(!['127.0.0.1','localhost'].includes(new URL(qa.url).hostname))throw Error('Only authorized local UI exports');
if(!qa.mobileFraming?.length)throw Error('Actual captured WebGL matrices required');
const arm=qa.inspection.arms[0],inputs={[qaPath]:hash(qaBytes)},rows=[];
const multiply=(m,p)=>[0,1,2,3].map(r=>m[r]*p[0]+m[r+4]*p[1]+m[r+8]*p[2]+m[r+12]*p[3]);
for(const camera of qa.mobileFraming){
 const url=new URL(arm[camera.stage].url,qa.url),response=await fetch(url);
 if(!response.ok)throw Error('Parameter HTTP '+response.status);
 const bytes=Buffer.from(await response.arrayBuffer()),b=JSON.parse(bytes.toString());inputs[url.href]=hash(bytes);
 if(![camera.modelViewMatrix,camera.projectionMatrix].every(m=>m.length===16&&m.every(Number.isFinite)))throw Error('Invalid actual camera matrix');
 let outside=0;const minimum=[Infinity,Infinity],maximum=[-Infinity,-Infinity];
 for(let i=0;i<b.count;i++){
  const raw=b.quats.slice(4*i,4*i+4),norm=Math.hypot(...raw),[w,x,y,z]=raw.map(v=>v/norm);
  const u=[1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)],v=[2*(x*y-w*z),1-2*(x*x+z*z),2*(y*z+w*x)];
  for(const [a,c] of [[-3,-3],[3,-3],[3,3],[-3,3]]){
   const point=[...u.map((value,k)=>b.xyz[3*i+k]-qa.inspection.center[k]+a*b.scales[3*i]*value+c*b.scales[3*i+1]*v[k]),1];
   const clip=multiply(camera.projectionMatrix,multiply(camera.modelViewMatrix,point)),ndc=[clip[0]/clip[3],clip[1]/clip[3]];
   if(!ndc.every(Number.isFinite))throw Error('Nonfinite projected triangle corner');
   if(ndc.some(x=>Math.abs(x)>1+1e-6))outside++;
   for(let k=0;k<2;k++){minimum[k]=Math.min(minimum[k],ndc[k]);maximum[k]=Math.max(maximum[k],ndc[k]);}
  }
 }
 rows.push({stage:camera.stage,count:b.count,checked_unique_quad_corners:b.count*4,outside_quad_corners:outside,ndc_min:minimum,ndc_max:maximum,outside_centers:camera.outsideCenters});
}
const source=await fs.readFile(new URL(import.meta.url));
const report={task_id:'PHD-P2-AB-V2-BROWSER-FULL-FIT-AUDIT',scientific_verdict:null,
 status:rows.every(r=>r.outside_quad_corners===0)?'PASS_DEFAULT_MOBILE_FULL_GAUSSIAN_QUAD_FIT':'FAIL_DEFAULT_MOBILE_QUAD_CLIPPING',
 scope:'Default arm initial/final at390px; saved Gaussian3sigma quad corners projected using actual captured WebGL projection/modelView matrices; UI framing only.',
 configuration:{qa_path:qaPath,output,url:qa.url,arm:arm.id,stages:qa.mobileFraming.map(r=>r.stage),sigma:3,ndc_tolerance:1e-6},
 source_sha256:hash(source),input_sha256:inputs,node:process.version,rows};
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
await fs.writeFile(path.join(path.dirname(output),'source_sample_browser_framing_audit.mjs'),source,{flag:'wx'});
console.log(JSON.stringify({status:report.status,rows}));
if(!report.status.startsWith('PASS'))process.exitCode=1;

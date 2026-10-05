// Full no-anchor display matrix, using the existing service and a dedicated software-GL browser.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';

const [url, output = '/out', ...flags] = process.argv.slice(2);
if (flags.some(flag=>flag!=='--allow-partial') || new Set(flags).size!==flags.length) throw Error('Only an explicit --allow-partial flag may relax result availability');
const allowPartial = flags.includes('--allow-partial');
const target = new URL(url);
const manifestPath = target.searchParams.get('manifest') || '';
if (target.protocol !== 'http:' || target.hostname !== '127.0.0.1' ||
    !/^\/task\/evaluation\/no_anchor_sfm_v1\/profiles\/[A-Za-z0-9_-]+\/manifest\.json$/.test(manifestPath)) throw Error('Exact local no-anchor profile URL required');
const conditions = ['SFM_noanchor_D005_Pnative_R22000', 'SFM_noanchor_D005_Pnative_R30000'];

export function availabilityPlan(manifest, allowPartial) {
  const ids=['SFM_noanchor_D005_Pnative_R22000','SFM_noanchor_D005_Pnative_R30000'];
  const states=[], galleries=[];
  const rows=manifest.condition_availability;
  if (allowPartial && (!Array.isArray(rows)||rows.length!==12)) throw Error('Partial QA requires the explicit twelve-row availability matrix');
  if (Array.isArray(rows)&&(rows.length!==12||new Set(rows.map(row=>row.region+'/'+row.candidate)).size!==12)) throw Error('Availability rows must be unique');
  for (const rid of ['P1','P2','P3']) {
    const region=manifest.regions.find(row=>row.id===rid);
    if (!region) throw Error('Missing region');
    for (const condition of ids) {
      for (const surface of ['raw','post']) {
        const id=condition+'.mesh_512.'+surface;
        const candidate=region.candidates.find(row=>row.id===id);
        if (!candidate) throw Error('A requested candidate is not explicitly registered');
        const row=rows?.find(item=>item.region===rid&&item.candidate===id);
        if (rows&&(!row||row.status!==candidate.status)) throw Error('Candidate and availability states disagree');
        if (candidate.status!=='available') {
          if (!allowPartial||!['pending','failed'].includes(candidate.status)) throw Error('Requested candidate is unavailable in strict QA');
          if (candidate.data!==null||candidate.mesh_data!==null||candidate.optimizer_updates!==null||!candidate.reason||!candidate.quality_status?.startsWith('NOT_ASSESSED_')||!candidate.provenance?.execution_attempt) throw Error('Unavailable candidate lacks explicit no-result provenance');
          if (candidate.status==='failed'&&!['train','export'].includes(candidate.failure_phase)) throw Error('Failure must declare the actual phase');
        }
        states.push({region:rid,condition,surface,id,status:candidate.status,available:candidate.status==='available'});
      }
      const montage=(region.renders||[]).find(item=>item.condition_id===condition);
      if (!montage&&!allowPartial) throw Error('Requested RGB evidence is missing in strict QA');
      galleries.push({region:rid,condition,available:!!montage});
    }
  }
  return {states,galleries,available_mesh_states:states.filter(row=>row.available).length,
    unavailable_mesh_states:states.filter(row=>!row.available).length,
    available_galleries:galleries.filter(row=>row.available).length,
    unavailable_galleries:galleries.filter(row=>!row.available).length};
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const profile = await fs.mkdtemp('/tmp/geogs-preview-');
const chromeLog = [], events = [], pending = new Map();
let browser, display, socket, sequence = 0;
const receipt = {schema:'GEOGS_NO_ANCHOR_BROWSER_QA_v1', scientific_verdict:null,
  status:'RUNNING', started_at:new Date().toISOString(), url, image_id:process.env.GEOGS_QA_IMAGE_ID,
  allow_partial_explicitly_requested:allowPartial,
  scope:'P1/P2/P3 × R22000/R30000 × raw/post actual mesh matrix, preserved Anchor512/native512, and one exact new RGB montage per region/condition. Technical display validation only.',
  regions:[], galleries:[], unavailable:[], unavailable_galleries:[], evidence:[], metadata:[], screenshots:[], checks:[]};
function check(pass, name, details) {
  receipt.checks.push({name, pass:!!pass, details});
  if (!pass) throw Error(name);
}
function send(method, params = {}) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {pending.delete(id); reject(Error('CDP timeout: '+method));}, 30000);
    pending.set(id, {resolve:value=>{clearTimeout(timeout); resolve(value);}, reject:error=>{clearTimeout(timeout); reject(error);}});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
}
async function ready(region, representation, condition, surface) {
  for (let i=0; i<600; i++) {
    const state = await evaluate('window.__GEOGS_QA || null');
    if (state?.errors?.length) throw Error(JSON.stringify(state.errors));
    if (state?.ready && (!region || state.region===region) && (!representation || state.representation_mode===representation) && (!condition || state.condition===condition) && (!surface || state.surface_mode===surface)) {
      await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
      return evaluate('window.__GEOGS_QA');
    }
    await pause(150);
  }
  throw Error('No-anchor ready timeout: '+region+'/'+condition+'/'+surface);
}
async function choose(id, value) {
  await evaluate(`(()=>{const el=document.getElementById(${JSON.stringify(id)});if(!el||![...el.options].some(o=>o.value===${JSON.stringify(value)}&&!o.disabled))throw Error('Missing option');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
}
async function pixels(state) {
  const rows = await evaluate(`(()=>[...document.querySelectorAll('.panel')].map(panel=>{const canvas=panel.querySelector('canvas'),gl=canvas.getContext('webgl2')||canvas.getContext('webgl'),missing=panel.querySelector('.missing');if(!gl)return {panel:panel.dataset.panel,webgl:false};const data=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,data);let different=0;for(let i=4;i<data.length;i+=4)if(data[i]!==data[0]||data[i+1]!==data[1]||data[i+2]!==data[2])different++;return {panel:panel.dataset.panel,webgl:true,width:canvas.width,height:canvas.height,nonbackground_pixels:different,missing_visible:!missing.hidden,missing_text:missing.textContent,links:[...panel.querySelectorAll('.panel-links a')].map(a=>a.href)};}))()`);
  check(rows.length===6, 'six_default_panels', state.region);
  for (const row of rows) {
    const panel = state.panels[row.panel];
    check(row.webgl && (panel.status==='available' ? panel.count>0 && panel.draw_calls>0 && row.nonbackground_pixels>10 : panel.count===0 && row.missing_visible && row.missing_text.length>0),
      'actual_pixels_or_explicit_unavailable', {region:state.region, status:panel.status, candidate:panel.candidate, ...row});
  }
  return rows;
}
async function capture(name) {
  const result = await send('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
  const bytes = Buffer.from(result.data,'base64');
  await fs.writeFile(path.join(output,name), bytes, {flag:'wx'});
  receipt.screenshots.push({filename:name, bytes:bytes.length, sha256:hash(bytes)});
}
async function stop(child) {
  if (!child || child.exitCode!==null || child.signalCode!==null) return;
  await new Promise(resolve=>{
    const timeout=setTimeout(()=>{child.kill('SIGKILL');},3000);
    child.once('close',()=>{clearTimeout(timeout);resolve();});
    child.kill('SIGTERM');
  });
}
const evidenceCache=new Map();
async function checkedEvidence(record, manifestURL) {
  const url=new URL(record.url||('/task/'+record.path),manifestURL);
  check(url.origin===target.origin&&url.pathname.startsWith('/task/')&&/^[0-9a-f]{64}$/.test(record.sha256||''),'local_exact_evidence_identity',record);
  const key=url.href+'#'+record.sha256;
  if (evidenceCache.has(key)) return evidenceCache.get(key);
  const response=await fetch(url);
  check(response.ok,'producer_evidence_http_ok',{url:url.href,status:response.status});
  const bytes=Buffer.from(await response.arrayBuffer());
  check(hash(bytes)===record.sha256&&(record.bytes===undefined||record.bytes===bytes.length),'producer_evidence_bytes_verified',{url:url.href,bytes:bytes.length,sha256:hash(bytes)});
  const value=url.pathname.endsWith('.json')?JSON.parse(bytes.toString()):null;
  const result={url:url.href,value,text:value===null?bytes.toString('utf8'):null};evidenceCache.set(key,result);
  receipt.evidence.push({url:url.href,sha256:hash(bytes),bytes:bytes.length});
  return result;
}
async function unavailableCandidate(candidate, panel, raster, region, condition, surface, manifestURL) {
  check(allowPartial&&['pending','failed'].includes(candidate.status),'unavailable_requires_explicit_partial_mode',{region,condition,surface});
  const attempt=candidate.provenance.execution_attempt;
  check(panel.candidate===candidate.id&&panel.status===candidate.status&&panel.representation==='none'&&panel.count===0&&panel.draw_calls===0&&panel.rendered_triangles===0&&panel.rendered_points===0&&panel.mesh_triangle_count===0&&panel.loaded_metadata.mesh===null&&panel.loaded_metadata.points===null,
    'unavailable_candidate_has_no_mesh_points_or_fallback',{region,condition,surface,panel});
  check(raster.missing_visible&&raster.missing_text===candidate.reason&&panel.reason===candidate.reason,'exact_unavailable_reason_visible',{region,condition,surface,reason:candidate.reason});
  check(attempt.target_optimizer_updates===Number(condition.split('_R').at(-1))&&attempt.optimizer_updates===null&&attempt.experiment_source_relative&&attempt.execution_attempt_id,'target_budget_is_not_claimed_as_completed',{region,condition,attempt});
  if (candidate.status==='failed') {
    const failure=await checkedEvidence(attempt.failure_receipt,manifestURL);
    check(failure.value?.status==='FAIL'&&failure.value.region===region&&failure.value.phase===candidate.failure_phase&&failure.value.condition_id==='SFM_noanchor_D005_Pnative'&&failure.value.scientific_verdict===null,
      'exact_failed_phase_receipt_without_quality_inference',{region,condition,failure:failure.value});
    check(raster.links.includes(failure.url),'failure_receipt_link_visible',{region,condition,url:failure.url});
  }
  let verifiedCudaOom=false;
  let verifiedHostMemoryFailure=false;
  for (const evidence of attempt.evidence||[]) {
    const loaded=await checkedEvidence(evidence,manifestURL);
    if (loaded.text && ['CUDA out of memory','CUDA error: out of memory'].some(message=>loaded.text.includes(message))) verifiedCudaOom=true;
    if (loaded.text && ['PINNED_HOST_BUDGET_EXCEEDED','_ArrayMemoryError','MemoryError:','std::bad_alloc',"DefaultCPUAllocator: can't allocate memory"].some(message=>loaded.text.includes(message))) verifiedHostMemoryFailure=true;
    check(raster.links.includes(loaded.url),'selected_attempt_evidence_link_visible',{region,condition,url:loaded.url});
    if (loaded.value?.phase) {
      check(loaded.value.region===region&&loaded.value.condition_id==='SFM_noanchor_D005_Pnative','selected_producer_evidence_region_condition',{region,condition,url:loaded.url});
      if (candidate.status==='pending') check(loaded.value.status!=='FAIL','older_failure_does_not_mask_pending_selected_attempt',{region,condition,url:loaded.url});
    }
  }
  if (candidate.failure_kind==='CUDA_OOM') check(verifiedCudaOom,'resource_failure_reason_backed_by_exact_native_log',{region,condition});
  if (candidate.failure_kind==='HOST_MEMORY_RESOURCE_FAILURE') check(verifiedHostMemoryFailure,'host_memory_failure_backed_by_exact_native_log',{region,condition});
  if (attempt.original_failed_run_receipt) {
    const prior=await checkedEvidence(attempt.original_failed_run_receipt,manifestURL);
    check(prior.value?.status==='FAIL'&&prior.value.region===region&&raster.links.includes(prior.url),'original_failed_attempt_preserved_separately',{region,condition,url:prior.url});
  }
  receipt.unavailable.push({region,condition,surface,candidate:candidate.id,status:candidate.status,
    failure_phase:candidate.failure_phase||null,quality_status:candidate.quality_status,reason:candidate.reason,attempt});
}
async function initializationFailureEvidence(attempt, raster, region, manifestURL) {
  const prior=attempt?.prior_initialization_failure;
  if (!prior) return;
  const failed=await checkedEvidence(prior.receipt,manifestURL);
  const log=await checkedEvidence(prior.log,manifestURL);
  check(prior.cause==='RESOURCE_SCHEDULING_ERROR'&&prior.classification==='CUDA_INITIALIZATION_FAILURE'&&prior.quality_assessed===false&&prior.cuda_oom_observed===true&&prior.counted_as_training_cuda_oom===false&&
    prior.first_step_record_absent===true&&prior.first_step_record_path===prior.receipt.path.replace(/receipt\.json$/,'model/jbgs_no_anchor/first_step.json')&&
    failed.value?.status==='FAIL'&&failed.value.native_exit_code===1&&failed.value.phase==='train'&&failed.value.region===region&&failed.value.condition_id==='SFM_noanchor_D005_Pnative'&&failed.value.scientific_verdict===null&&log.text?.includes('CUDA error: out of memory'),
    'prior_initialization_failure_is_separate_exact_producer_evidence',{region,prior});
  check(raster.links.includes(failed.url)&&raster.links.includes(log.url),'prior_initialization_failure_links_visible',{region,receipt:failed.url,log:log.url});
}
async function finalRetryEvidence(attempt,raster,region,manifestURL) {
  const row=attempt?.final_resource_retry;
  if (attempt?.execution_attempt_id?.startsWith('no_anchor_sfm_gradient_memory_v3_')) check(Boolean(row),'final_retry_policy_metadata_required',{region});
  if (!row) return;
  const loaded={};
  for (const key of ['policy','predecessor_training_receipt','predecessor_native_log','predecessor_amendment','predecessor_first_step']) {
    loaded[key]=await checkedEvidence(row[key],manifestURL);
    check(raster.links.includes(loaded[key].url),'final_retry_evidence_link_visible',{region,key,url:loaded[key].url});
  }
  const policy=loaded.policy.value,parent=loaded.predecessor_training_receipt.value,first=loaded.predecessor_first_step.value;
  check(row.policy.sha256==='edf3f4312c622059a3506c6ca1c07d2b1c90e234fb672cc592ea3ea7e28f5a9a'&&policy.schema==='GEOGS_SFM_FINAL_RESOURCE_RETRY_POLICY_v1'&&policy.scientific_verdict===null&&policy.maximum_additional_fresh_training_attempts_per_region===1&&policy.retry_attempts[region]===attempt.execution_attempt_id&&policy.selected_predecessors[region]===row.predecessor_attempt_id&&row.region===region&&row.attempt_index===1&&row.max_attempts===1&&row.resource_recovery_version===3&&row.storage_version===2&&row.fresh_only===true&&row.resume===false&&row.automatic_further_retry===false&&row.quality_based_selection===false&&row.historical_prefix_replacement_allowed===false,
    'one_fixed_fresh_resource_retry_policy_bound',{region,row});
  check(parent.status==='FAIL'&&[1,-9].includes(parent.native_exit_code)&&parent.validated_exit_code===parent.native_exit_code&&parent.region===region&&parent.phase==='train'&&parent.condition_id==='SFM_noanchor_D005_Pnative'&&parent.scientific_verdict===null&&['started_unix','finished_unix','wall_seconds'].every(key=>Number.isFinite(parent[key])&&parent[key]>=0)&&parent.finished_unix>=parent.started_unix&&first.status==='PASS_FIRST_STEP_DIRECT_REFINEMENT'&&first.iteration===1&&first.anchor_iterations_executed===0&&first.pretrained_optimizer_loaded===false&&first.stage2_active===true&&first.scientific_verdict===null,
    'final_retry_predecessor_is_actual_closed_failed_training_with_first_step',{region,parent,first});
  let verifiedCgroup=false;
  if (row.predecessor_resource_failure) {
    const failure=await checkedEvidence(row.predecessor_resource_failure,manifestURL),proof=failure.value;
    check(raster.links.includes(failure.url),'predecessor_cgroup_failure_receipt_link_visible',{region});
    const texts={},metadata=row.resource_failure_evidence||[];
    for (const item of proof.evidence||[]) {
      const evidence=await checkedEvidence(item,manifestURL);
      if (!['kernel_journal','docker_inspect','docker_inspect_command'].includes(item.role)) continue;
      check(!(item.role in texts),'unique_cgroup_causal_evidence_role',{region,role:item.role});
      check(metadata.some(record=>['role','path','bytes','sha256'].every(key=>record[key]===item[key]))&&raster.links.includes(evidence.url),
        'cgroup_evidence_bytes_and_download_match_bound_proof',{region,role:item.role});
      texts[item.role]=evidence.text??JSON.stringify(evidence.value);
    }
    const container=proof.container_id,victim=proof.victim_pid,kernel=texts.kernel_journal||'',inspect=texts.docker_inspect||'',inspectCommand=texts.docker_inspect_command||inspect;
    verifiedCgroup=proof.schema==='GEOGS_NATIVE_RESOURCE_FAILURE_v1'&&proof.scientific_verdict===null&&proof.region===region&&proof.condition_id==='SFM_noanchor_D005_Pnative'&&proof.native_exit_code===-9&&parent.native_exit_code===-9&&proof.cause==='CGROUP_OOM_KILL'&&proof.kernel_oom_confirmed===true&&proof.producer_receipt_sha256===row.predecessor_training_receipt.sha256&&/^[a-f0-9]{64}$/.test(container)&&Number.isInteger(victim)&&victim>0&&proof.limit_bytes===34359738368&&proof.cgroup_path==='/system.slice/docker-'+container+'.scope'&&metadata.length===Object.keys(texts).length&&[2,3].includes(Object.keys(texts).length)&&kernel.includes('constraint=CONSTRAINT_MEMCG')&&kernel.includes(proof.cgroup_path)&&kernel.includes('task=python,pid='+victim+',')&&kernel.includes('Memory cgroup out of memory: Killed process '+victim+' (python)')&&kernel.includes('memory: usage 33554432kB, limit 33554432kB')&&inspect.includes(container)&&inspectCommand.includes('jbgs-geogs-'+row.predecessor_attempt_id+'-'+region+'-train')&&row.predecessor_resource_failure_classification==='CGROUP_OOM_KILL';
    check(verifiedCgroup,'predecessor_sigkill_bound_to_kernel_cgroup_and_container',{region});
  }
  check(verifiedCgroup||['CUDA out of memory','CUDA error: out of memory','torch.cuda.OutOfMemoryError','PINNED_HOST_BUDGET_EXCEEDED','_ArrayMemoryError','MemoryError:','std::bad_alloc',"DefaultCPUAllocator: can't allocate memory"].some(token=>loaded.predecessor_native_log.text?.includes(token)),
    'final_retry_resource_failure_backed_by_original_log',{region});
}
try {
  display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1240x24','-nolisten','tcp']);
  display.stderr.on('data',bytes=>chromeLog.push('Xvfb: '+bytes));
  const number=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Xvfb timeout')),10000);
    display.stdout.once('data',bytes=>{clearTimeout(timer);const value=bytes.toString().trim(); /^\d+$/.test(value)?resolve(value):reject(Error('Invalid display'));});
    display.once('error',reject);
  });
  receipt.dedicated_xvfb_display=number;
  for (const suffix of ['config','cache','data']) await fs.mkdir(profile+'/'+suffix);
  const args=['--headless=new','--no-sandbox','--no-first-run','--no-default-browser-check','--enable-automation','--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'];
  receipt.chrome_args=args;
  receipt.software_webgl='Dedicated Docker Xvfb and software ANGLE GL; no host display or GPU device';
  browser=spawn(process.env.CHROME_BIN||'/usr/bin/chromium',args,{env:{...process.env,DISPLAY:':'+number,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',bytes=>chromeLog.push(bytes.toString()));
  let port;
  for (let i=0;i<150;i++) {try {port=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;} catch {await pause(100);}}
  if (!port) throw Error('Dedicated Chrome start timeout');
  const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(pages.find(item=>item.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const item=pending.get(message.id);if(item){pending.delete(message.id);message.error?item.reject(Error(JSON.stringify(message.error))):item.resolve(message.result);}}else events.push(message);});
  receipt.browser=await send('Browser.getVersion');
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1240,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url});
  const first=await ready();
  const response=await fetch(first.manifest);
  check(response.ok,'manifest_http_ok',response.status);
  const bytes=Buffer.from(await response.arrayBuffer()), manifest=JSON.parse(bytes.toString());
  await fs.writeFile(path.join(output,'served_manifest.json'),bytes,{flag:'wx'});
  receipt.manifest={url:first.manifest,sha256:hash(bytes),bytes:bytes.length};
  check(hash(bytes)===process.env.GEOGS_QA_MANIFEST_SHA256,'served_manifest_matches_frozen_snapshot',receipt.manifest);
  check(manifest.scientific_verdict===null && JSON.stringify(manifest.regions.map(item=>item.id))===JSON.stringify(['P1','P2','P3']),'three_regions_null_verdict',manifest.regions.map(item=>item.id));
  check(manifest.resolution_modes.length===1&&manifest.resolution_modes[0].id==='512','matched_resolution_512_only',manifest.resolution_modes);
  const plan=availabilityPlan(manifest,allowPartial);
  receipt.expected_availability=plan;
  const metadataCache=new Map();
  for (const region of ['P1','P2','P3']) {
    const regional=manifest.regions.find(item=>item.id===region);
    check(regional.conditions.length===8&&conditions.every(id=>regional.conditions.some(c=>c.id===id))&&regional.conditions.some(c=>c.id==='D005_Pnative'),'six_original_plus_two_new_conditions',regional.conditions.map(c=>c.id));
    await choose('region-select',region); await ready(region);
    await choose('resolution-select','512'); await ready(region);
    await choose('representation-select','mesh'); await ready(region,'mesh');
    for (const condition of conditions) {
      await choose('condition-select',condition); await ready(region,'mesh',condition);
      for (const surface of ['raw','post']) {
        await choose('surface-select',surface);
        const state=await ready(region,'mesh',condition,surface);
        check(state.mesh_res===512&&state.resolution_mode==='512','actual_mesh_res_512',{region,condition,surface});
        const raster=await pixels(state);
        const expected={anchor:'D005_Pnative.anchor_512.'+surface,vanilla:'D005_Pnative.mesh_512.'+surface,changed:condition+'.mesh_512.'+surface};
        for (const [key,id] of Object.entries(expected)) {
          const panel=state.panels[key], candidate=regional.candidates.find(c=>c.id===id);
          if (key==='changed') await initializationFailureEvidence(candidate?.provenance?.execution_attempt,raster.find(row=>row.panel===key),region,first.manifest);
          if (key==='changed') await finalRetryEvidence(candidate?.provenance?.execution_attempt,raster.find(row=>row.panel===key),region,first.manifest);
          if (key==='changed'&&candidate?.status!=='available') {
            await unavailableCandidate(candidate,panel,raster.find(row=>row.panel===key),region,condition,surface,first.manifest);
            continue;
          }
          check(candidate?.status==='available'&&panel.candidate===id&&panel.status==='available','exact_available_candidate_without_fallback',{region,condition,surface,key,id,panel});
          check(panel.representation==='mesh'&&panel.mesh_triangle_count>0&&panel.rendered_triangles===panel.mesh_triangle_count&&panel.draw_calls>0&&panel.mesh_binary_integrity==='SHA256_AND_BYTES_VERIFIED','actual_binary_triangles_verified_and_drawn',{region,condition,surface,key,panel});
          const metadataURL=new URL(candidate.mesh_data.url,first.manifest).href;
          check(new URL(metadataURL).origin===target.origin,'local_metadata_origin',metadataURL);
          if (!metadataCache.has(metadataURL)) {
            const reply=await fetch(metadataURL);
            check(reply.ok,'metadata_http_ok',{url:metadataURL,status:reply.status});
            const buffer=Buffer.from(await reply.arrayBuffer());
            metadataCache.set(metadataURL,JSON.parse(buffer.toString()));
            receipt.metadata.push({url:metadataURL,sha256:hash(buffer),bytes:buffer.length});
          }
          const actual=panel.loaded_metadata.mesh, declared=metadataCache.get(metadataURL);
          check(JSON.stringify(actual)===JSON.stringify(declared)&&actual.source_mesh?.sha256&&actual.topology_simplified===false&&actual.artificial_clip_caps===false,'loaded_metadata_matches_original_binary_provenance',{region,condition,surface,key,source_mesh:actual.source_mesh});
        }
        receipt.regions.push({region,condition,surface,state,raster});
        await evaluate('window.scrollTo(0,0)');
        await capture(region+'_'+condition+'_'+surface+'_mesh.png');
      }
      const expected=(regional.renders||[]).find(item=>item.condition_id===condition);
      if (!expected) {
        check(allowPartial,'missing_rgb_requires_explicit_partial_mode',{region,condition});
        const shown=await evaluate(`(()=>({selected:document.getElementById('render-select').value,src:document.getElementById('render-image').getAttribute('src'),hidden:document.getElementById('render-figure').hidden}))()`);
        const registered=(regional.renders||[]).find(item=>item.id===shown.selected);
        check(shown.hidden||registered&&!registered.condition_id&&registered.source_condition_id&&registered.label.includes(registered.source_condition_id),
          'baseline_gallery_is_labeled_and_not_substituted_as_new_rgb',{region,condition,shown,registered});
        receipt.unavailable_galleries.push({region,condition,status:'NOT_ASSESSED_NEW_CONDITION_RGB_UNAVAILABLE',
          reason:'No actual new-condition montage is registered in the frozen profile',baseline_gallery:registered||null});
        continue;
      }
      check(true,'new_condition_rgb_montage_registered',{region,condition});
      await choose('render-domain-select',expected.domain||'unspecified');
      await choose('render-image-select',expected.image_name||expected.id);
      await choose('render-select',expected.id);
      const expectedURL=new URL(expected.url||expected.path,first.manifest).href;
      let gallery;
      for(let i=0;i<300;i++) {
        gallery=await evaluate(`(()=>{const figure=document.getElementById('render-figure'),img=document.getElementById('render-image');return {hidden:figure.hidden,src:img.src,complete:img.complete,width:img.naturalWidth,height:img.naturalHeight,caption:document.getElementById('render-caption').textContent,selected:document.getElementById('render-select').value,domain:document.getElementById('render-domain-select').value,photo:document.getElementById('render-image-select').value};})()`);
        if(!gallery.hidden&&gallery.complete&&gallery.width>0&&gallery.height>0&&gallery.src===expectedURL) break;
        await pause(100);
      }
      check(!gallery.hidden&&gallery.complete&&gallery.width>0&&gallery.height>0&&gallery.selected===expected.id&&gallery.src===expectedURL&&new URL(gallery.src).origin===target.origin,'exact_new_condition_rgb_montage_loaded',{region,condition,gallery,source:expected});
      receipt.galleries.push({region,condition,gallery,source:expected});
      await evaluate("document.getElementById('render-figure').scrollIntoView({block:'start'});new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
      await capture(region+'_'+condition+'_RGB.png');
    }
  }
  const failed=events.filter(event=>event.method==='Runtime.exceptionThrown'||(event.method==='Network.loadingFailed'&&event.params.errorText!=='net::ERR_ABORTED')||(event.method==='Network.responseReceived'&&event.params.response.status>=400));
  receipt.aborted_requests=events.filter(event=>event.method==='Network.loadingFailed'&&event.params.errorText==='net::ERR_ABORTED');
  check(failed.length===0,'no_browser_exception_http_error_or_nonabort_failure',failed);
  const actualMeshes=receipt.regions.filter(row=>row.state.panels.changed.status==='available').length;
  check(receipt.regions.length===plan.states.length&&actualMeshes===plan.available_mesh_states&&receipt.unavailable.length===plan.unavailable_mesh_states&&receipt.galleries.length===plan.available_galleries&&receipt.unavailable_galleries.length===plan.unavailable_galleries&&receipt.screenshots.length===plan.states.length+plan.available_galleries,
    'requested_display_matrix_accounted_without_imputed_outputs',{mesh_states:receipt.regions.length,actual_mesh_states:actualMeshes,unavailable_mesh_states:receipt.unavailable.length,galleries:receipt.galleries.length,unavailable_galleries:receipt.unavailable_galleries.length,screenshots:receipt.screenshots.length});
  const incomplete=plan.unavailable_mesh_states>0||plan.unavailable_galleries>0;
  receipt.status=incomplete?'PARTIAL_NO_ANCHOR_BROWSER_QA':'PASS_NO_ANCHOR_BROWSER_QA';
  receipt.technical_display_checks_passed=true;
  receipt.requested_result_matrix_complete=!incomplete;
  receipt.exit_code_semantics='Zero means the declared actual/unavailable display states passed technical checks; PARTIAL never means all experiment outputs exist.';
} catch(error) {
  receipt.status='FAIL_NO_ANCHOR_BROWSER_QA'; receipt.error=String(error);process.exitCode=1;
} finally {
  if(socket) socket.close();
  await stop(browser); await stop(display);
  receipt.completed_at=new Date().toISOString();
  await fs.writeFile(path.join(output,'chrome.log'),chromeLog.join(''),{flag:'wx'});
  await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:receipt.status,screenshots:receipt.screenshots.length,checks:receipt.checks.length,error:receipt.error||null}));
}

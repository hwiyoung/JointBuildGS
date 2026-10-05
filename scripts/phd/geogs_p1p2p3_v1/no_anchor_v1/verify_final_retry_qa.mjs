// Small QA-contract fixtures with read-only bound producer records; no browser/GPU.
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
const [source,task,consumerReceipt,output]=process.argv.slice(2);
const code=await fs.readFile(source,'utf8');
const consumer=JSON.parse(await fs.readFile(consumerReceipt,'utf8'));
const start=code.indexOf('async function finalRetryEvidence('),end=code.indexOf('\ntry {',start);
if(start<0||end<start)throw Error('Missing final retry QA helper');
const checks=[],overrides=new Map();let assertions=0;
const hash=data=>crypto.createHash('sha256').update(data).digest('hex');
function check(name,value){checks.push({name,passed:!!value});if(!value)throw Error(name);}
async function reject(name,fn){try{await fn();}catch{check(name,true);return;}check(name,false);}
async function checkedEvidence(record){
  if(!record?.path||path.isAbsolute(record.path)||record.path.split('/').includes('..'))throw Error('Contained evidence required');
  const bytes=await fs.readFile(path.join(task,record.path));
  if(hash(bytes)!==record.sha256||(record.bytes!==undefined&&record.bytes!==bytes.length))throw Error('Evidence digest differs');
  const value=record.path.endsWith('.json')?JSON.parse(bytes.toString()):null;
  return {url:'http://localhost:8902/task/'+record.path,value:overrides.get(record.path)??value,text:value===null?bytes.toString():null};
}
const context=vm.createContext({checkedEvidence,check:(pass,name)=>{assertions++;if(!pass)throw Error(name);}});
vm.runInContext(code.slice(start,end),context);
function fixture(record){
  const row=structuredClone(record.final_resource_retry);
  const attempt={execution_attempt_id:'no_anchor_sfm_gradient_memory_v3_'+record.region,final_resource_retry:row};
  const paths=['policy','predecessor_training_receipt','predecessor_native_log','predecessor_amendment','predecessor_first_step']
    .map(key=>row[key].path);
  if(row.predecessor_resource_failure){paths.push(row.predecessor_resource_failure.path);paths.push(...row.resource_failure_evidence.map(item=>item.path));}
  return {attempt,raster:{links:paths.map(relative=>'http://localhost:8902/task/'+relative)},region:record.region};
}
const run=f=>context.finalRetryEvidence(f.attempt,f.raster,f.region,'http://localhost:8902/');
const records=consumer.actual_readonly_amendment_bindings;
for(const record of records){const f=fixture(record);await run(f);check('actual_'+record.region+'_bound_policy_links_and_resource_cause',true);}
if(records.length<2)throw Error('Both actual P1/P2 preparation records required');
const original=records[0];
for(const [key,value] of [['max_attempts',2],['resume',true],['region','P3'],['historical_prefix_replacement_allowed',true],['quality_based_selection',true]]){
  const f=fixture(original);f.attempt.final_resource_retry[key]=value;
  await reject('reject_invalid_'+key,()=>run(f));
}
let f=fixture(original);delete f.attempt.final_resource_retry;await reject('final_attempt_missing_policy_is_rejected',()=>run(f));
f=fixture(original);f.raster.links.pop();await reject('missing_visible_predecessor_evidence_link_is_rejected',()=>run(f));
f=fixture(original);f.attempt.final_resource_retry.predecessor_native_log.sha256='0'.repeat(64);
await reject('changed_native_evidence_bytes_rejected',()=>run(f));
f=fixture(original);
let parent=structuredClone((await checkedEvidence(f.attempt.final_resource_retry.predecessor_training_receipt)).value);
parent.native_exit_code=-15;parent.validated_exit_code=-15;
overrides.set(f.attempt.final_resource_retry.predecessor_training_receipt.path,parent);
await reject('intentional_sigterm_not_reclassified_as_final_retry_failure',()=>run(f));overrides.clear();
const cgroupRecord=records.find(row=>row.final_resource_retry.predecessor_resource_failure);
if(!cgroupRecord)throw Error('Actual bound P2 kernel/cgroup fixture required');
f=fixture(cgroupRecord);
delete f.attempt.final_resource_retry.predecessor_resource_failure;delete f.attempt.final_resource_retry.resource_failure_evidence;
await reject('sigkill_without_kernel_proof_is_not_memory_failure',()=>run(f));
for(const [key,value] of [['victim_pid',1],['kernel_oom_confirmed',false],['limit_bytes',17179869184],['producer_receipt_sha256','0'.repeat(64)]]){
  const f=fixture(cgroupRecord),row=f.attempt.final_resource_retry;
  const proof=structuredClone((await checkedEvidence(row.predecessor_resource_failure)).value);proof[key]=value;
  overrides.set(row.predecessor_resource_failure.path,proof);
  await reject('reject_cgroup_'+key,()=>run(f));overrides.clear();
}
await context.finalRetryEvidence({execution_attempt_id:'no_anchor_sfm_memory_recovery_v2'},{links:[]},'P1','http://localhost/');
check('legacy_attempts_require_no_new_final_policy',true);
await fs.writeFile(output,JSON.stringify({status:'PASS_READONLY_QA_CONTRACT_FIXTURES',scientific_verdict:null,
  actual_scene_quality_evaluated:false,browser_launched:false,gpu_used:false,checks,check_count:checks.length,
  exercised_helper_assertions:assertions,source_sha256:hash(code),consumer_receipt_sha256:hash(await fs.readFile(consumerReceipt))},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({status:'PASS_READONLY_QA_CONTRACT_FIXTURES',checks:checks.length}));

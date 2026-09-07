// Pure in-memory QA-contract fixtures; no Chromium, HTTP or scene outputs.
import fs from 'node:fs/promises';
import vm from 'node:vm';
import crypto from 'node:crypto';
const [source,output]=process.argv.slice(2);
const code=await fs.readFile(source,'utf8'),checks=[];
function check(name,value){checks.push({name,pass:!!value});if(!value)throw Error(name);}
function reject(name,fn){try{fn();}catch{check(name,true);return;}check(name,false);}
const fn=code.slice(code.indexOf('export function availabilityPlan'),code.indexOf('const pause')).replace('export function','function');
const context=vm.createContext({});vm.runInContext(fn,context);
const condition='SFM_noanchor_D005_Pnative_PREFIX8000';
const manifest={regions:[],condition_availability:[]};
for(const region of ['P1','P2','P3']){
  const record={id:region,candidates:[],renders:[{condition_id:condition}]};
  for(const kind of ['raw','post']){
    const id=condition+'.mesh_512.'+kind;
    record.candidates.push({id,status:'available'});
    manifest.condition_availability.push({region,candidate:id,status:'available'});
  }
  manifest.regions.push(record);
}
const full=context.availabilityPlan(manifest,false);
check('strict_fixed_budget_matrix_is_six_mesh_three_RGB',full.available_mesh_states===6&&full.available_galleries===3);
const partial=structuredClone(manifest);
for(const region of partial.regions.slice(1)){
  region.renders=[];
  for(const candidate of region.candidates){
    candidate.status=region.id==='P2'?'failed':'pending';
    Object.assign(candidate,{data:null,mesh_data:null,optimizer_updates:null,reason:'Explicit prefix state',quality_status:'NOT_ASSESSED_PREFIX',failure_phase:region.id==='P2'?'prefix_validation':null,provenance:{execution_attempt:{}}});
    partial.condition_availability.find(row=>row.region===region.id&&row.candidate===candidate.id).status=candidate.status;
  }
}
const plan=context.availabilityPlan(partial,true);
check('partial_counts_actual_two_unavailable_four_and_one_RGB',plan.available_mesh_states===2&&plan.unavailable_mesh_states===4&&plan.available_galleries===1&&plan.unavailable_galleries===2);
reject('strict_default_rejects_missing_prefixes',()=>context.availabilityPlan(partial,false));
const fallback=structuredClone(partial);fallback.regions[1].candidates[0].data={url:'/old'};
reject('unavailable_prefix_may_not_fallback_to_old_data',()=>context.availabilityPlan(fallback,true));
const duplicate=structuredClone(partial);duplicate.condition_availability[1]=duplicate.condition_availability[0];
reject('duplicate_availability_identity_rejected',()=>context.availabilityPlan(duplicate,true));
const wrongPhase=structuredClone(partial);wrongPhase.regions[1].candidates[0].failure_phase='train';
reject('parent_train_failure_cannot_replace_prefix_failure_phase',()=>context.availabilityPlan(wrongPhase,true));
const helper=code.slice(code.indexOf('async function parentAndPrefixEvidence'),code.indexOf('async function initializationFailureEvidence'));
const records=new Map();
const parent={url:'http://127.0.0.1:8902/task/parent.json',value:{status:'FAIL',native_exit_code:1,region:'P1',phase:'train',scientific_verdict:null}};
const prefix={url:'http://127.0.0.1:8902/task/prefix.json',value:{status:'PREFIX_8000_VALIDATED',actual_optimizer_updates:8000,planned_total_updates:30000,region:'P1',scientific_verdict:null}};
records.set('parent',parent);records.set('prefix',prefix);
const proofContext=vm.createContext({checkedEvidence:async row=>records.get(row.path),check:(pass,name)=>check(name,pass)});
vm.runInContext(helper,proofContext);
const candidate={status:'available',optimizer_updates:8000,provenance:{execution_attempt:{analysis_role:'SUPPLEMENTARY_PREFIX_DIAGNOSTIC',planned_total_updates:30000,full_experiment_completion_inferred:false,parent_training_status:'FAIL',parent_training_receipt:{path:'parent'},prefix_validation_receipt:{path:'prefix'}}}};
await proofContext.parentAndPrefixEvidence(candidate,{links:[parent.url,prefix.url]},'P1','http://127.0.0.1:8902/');
check('available_prefix_with_failed_parent_is_supported',true);
const bad=structuredClone(candidate);bad.provenance.execution_attempt.full_experiment_completion_inferred=true;
let rejected=false;try{await proofContext.parentAndPrefixEvidence(bad,{links:[parent.url,prefix.url]},'P1','http://127.0.0.1:8902/');}catch{rejected=true;}
// A deliberately failing check is part of this negative fixture, not a QA failure.
checks.pop();check('prefix_must_not_imply_full_completion',rejected);
await fs.writeFile(output,JSON.stringify({status:'PASS_SYNTHETIC_PREFIX_QA_CONTRACT',scientific_verdict:null,checks,check_count:checks.length,
  source_sha256:crypto.createHash('sha256').update(code).digest('hex'),scope:'Pure synthetic in-memory validation; no browser or actual GeoGS result'},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({status:'PASS_SYNTHETIC_PREFIX_QA_CONTRACT',checks:checks.length}));

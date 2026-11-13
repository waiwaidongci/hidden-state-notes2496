<script setup lang="ts">
import {ref,computed,watch} from 'vue';
import PageTitle from '../components/common/PageTitle.vue';
import Empty from '../components/common/Empty.vue';
import Status from '../components/common/Status.vue';
import Table from '../components/common/Table.vue';
import Notice from '../components/common/Notice.vue';
import {comparisonApi} from '../api/comparison';
import {useTask} from '../hooks/useTask';
import {fmt} from '../utils/format';
const p=defineProps<{studies:any[];traces:any[];profiles:any[];comparisons:any[];user:any}>();
const id=ref(0),name=ref('模型对比 '+new Date().toLocaleTimeString()),picked=ref<number[]>([]),baselineId=ref(0),selectedTraceIds=ref<number[]|null>(null),task=useTask(),openId=ref(0);
const study=computed(()=>p.studies.find(s=>s.id===(id.value||p.studies[0]?.id)));
const rows=computed(()=>p.traces.filter(t=>t.study_id===study.value?.id));
const symbolKey=(syms:string[])=>[...syms].sort().join('|');
const studyName=(sid:number)=>p.studies.find(s=>s.id===sid)?.name||('研究'+sid);
// 候选可跨研究：只要观测码集合与对比研究相同（码序、状态数不限）
const available=computed(()=>{
 const key=study.value?symbolKey(study.value.symbols):'';
 return p.profiles.filter(m=>symbolKey(m.symbols)===key);
});
watch(study,()=>{picked.value=[];baselineId.value=0;selectedTraceIds.value=null},{immediate:true});
watch(available,(list)=>{
 const keep=new Set(list.map(m=>m.id));
 picked.value=picked.value.filter(v=>keep.has(v));
 if(baselineId.value&&!keep.has(baselineId.value))baselineId.value=0;
});
const traceIds=computed(()=>selectedTraceIds.value===null?rows.value.slice(0,20).map(t=>t.id):selectedTraceIds.value);
function toggleProfile(pid:number){
 if(picked.value.includes(pid))picked.value=picked.value.filter(v=>v!==pid);
 else picked.value=[...picked.value,pid];
}
function toggleTrace(tid:number){
 selectedTraceIds.value=traceIds.value.includes(tid)?traceIds.value.filter(v=>v!==tid):[...traceIds.value,tid];
}
const detail=computed(()=>{
 const list=p.comparisons.filter(c=>c.study_id===study.value?.id);
 return list.find(c=>c.id===openId.value)||list[0];
});
async function submit(){
 const baseline=baselineId.value||picked.value[0];
 await task.act(async()=>{
  const c=await comparisonApi.create({study_id:study.value.id,name:name.value,baseline_profile_id:baseline,profile_ids:picked.value,trace_ids:traceIds.value});
  openId.value=c.id;
 },'共用冻结观测的模型对比已排队');
}
function deltaClass(v:number|null){return v===null?'':v>0?'delta-pos':v<0?'delta-neg':''}
</script>
<template>
 <PageTitle index="05" title="同一批冻结观测，哪个版本更讲得通。" description="候选版本共用观测快照，按累计对数似然排序，逐轨迹列出相对基准版本的logL差值。"/>
 <label>对比研究<select :value="study?.id||0" @change="id=Number(($event.target as HTMLSelectElement).value)"><option v-for="s in studies" :key="s.id" :value="s.id">{{s.name}}</option></select></label>
 <div class="config-layout">
  <form class="input-panel" @submit.prevent="submit">
   <small>01 / FROZEN MODEL CANDIDATES</small>
   <h2>选择候选版本</h2>
   <label>对比名称<input v-model="name" required/></label>
   <p>候选须观测码集合相同；码排列顺序与状态数可不同。已选{{picked.length}}/8个版本。</p>
   <p v-if="!available.length" class="copper">没有与该研究观测码集合相同的候选版本；可先在“固定模型推断”冻结同码集合版本（码序与状态数不限）。</p>
   <div class="trace-picker profile-picker">
    <label v-for="m in available" :key="m.id">
     <input type="checkbox" :checked="picked.includes(m.id)" @change="toggleProfile(m.id)"/>
     <span>{{m.name}}<small>{{m.version}} / {{m.states.length}}态 / {{studyName(m.study_id)}} / 码序 {{m.symbols.join(' ')}}</small></span>
    </label>
   </div>
   <label v-if="picked.length">基准版本（差值口径）<select :value="baselineId||picked[0]" @change="baselineId=Number(($event.target as HTMLSelectElement).value)"><option v-for="pid in picked" :key="pid" :value="pid">{{available.find(m=>m.id===pid)?.name}}</option></select></label>
  </form>
  <form class="selection-panel" @submit.prevent="submit">
   <small>02 / SHARED FROZEN OBSERVATIONS</small>
   <h2>共用观测轨迹</h2>
   <p>已选{{traceIds.length}}/30条；默认前20条。排队时冻结快照，之后修订观测不改变本对比。</p>
   <div class="selection-actions">
    <button type="button" @click="selectedTraceIds=rows.slice(0,20).map(t=>t.id)">默认前20条</button>
    <button type="button" @click="selectedTraceIds=[]">清空选择</button>
   </div>
   <div class="trace-picker">
    <label v-for="t in rows" :key="t.id"><input type="checkbox" :checked="traceIds.includes(t.id)" @change="toggleTrace(t.id)"/><span>{{t.reference}}<small>{{t.tokens.length}}码 / {{t.tokens.slice(0,8).join(' ')}}</small></span></label>
   </div>
   <button v-if="user.role!=='viewer'" class="primary" :disabled="task.state.busy||picked.length<2||picked.length>8||traceIds.length<1||traceIds.length>30">送入模型对比队列 →</button>
   <p v-else>观察员只读对比结果。</p>
  </form>
 </div>
 <Notice v-bind="task.state"/>
 <section class="section">
  <h2>对比归档</h2>
  <Table :headers="['对比名称','状态','版本/轨迹数','基准版本','打开']">
   <tr v-for="c in comparisons.filter(x=>x.study_id===study?.id)" :key="c.id">
    <td><strong>{{c.name}}</strong><small>#{{c.id}}</small></td>
    <td><Status :value="c.status"/><small v-if="c.error" class="copper">{{c.error}}</small></td>
    <td>{{c.profile_snapshots.length}}版本 / {{c.trace_snapshot.length}}轨迹</td>
    <td>{{c.profile_snapshots.find((m:any)=>m.id===c.baseline_profile_id)?.name}}</td>
    <td><button @click="openId=c.id">展开对比 ↗</button></td>
   </tr>
  </Table>
 </section>
 <template v-if="detail?.result">
  <div class="record-title"><small>COMPARISON / #{{detail.id}}</small><h2>{{detail.name}}</h2></div>
  <p class="snapshot-line">冻结指纹 <span class="fingerprint">{{detail.result.fingerprint}}</span></p>
  <section class="section">
   <h2>版本排序（按可解释轨迹累计logL降序）</h2>
   <Table :headers="['名次','版本','状态数','可解释/不可解释','累计logL','相对基准累计差值']">
    <tr v-for="r in detail.result.ranking" :key="r.profile_id">
     <td>{{r.rank===null?'—':'#'+r.rank}}<small v-if="r.profile_id===detail.baseline_profile_id">基准</small></td>
     <td>{{r.profile_name}}<small>{{r.profile_version}}</small></td>
     <td>{{r.state_count}}</td>
     <td>{{r.explainable_count}} / {{r.unexplainable_count}}</td>
     <td>{{r.total_log_likelihood===null?'不可解释':fmt(r.total_log_likelihood,6)}}</td>
     <td :class="deltaClass(r.profile_id===detail.baseline_profile_id?0:detail.result.versions.find((v:any)=>v.profile_id===r.profile_id)?.total_delta_vs_baseline)">{{r.total_log_likelihood===null?'—':fmt(detail.result.versions.find((v:any)=>v.profile_id===r.profile_id)?.total_delta_vs_baseline,6)}}</td>
    </tr>
   </Table>
  </section>
  <section class="section">
   <h2>逐轨迹相对基准差值</h2>
   <Table :headers="['轨迹','码数',...detail.result.ranking.map((r:any)=>r.profile_name+(r.profile_id===detail.baseline_profile_id?'（基准）':''))]">
    <tr v-for="(refName,i) in detail.result.trace_order" :key="refName">
     <td>{{refName}}</td>
     <td>{{detail.result.versions[0].per_trace[i].token_count}}</td>
     <td v-for="v in detail.result.versions" :key="v.profile_id">
      <template v-if="!v.per_trace[i].explainable"><span class="copper">不可解释</span><small>{{v.per_trace[i].impossible_reason}}</small></template>
      <template v-else>
       <strong :class="deltaClass(v.per_trace[i].delta_vs_baseline)">{{fmt(v.per_trace[i].log_likelihood,5)}}</strong>
       <small>Δ {{v.per_trace[i].delta_vs_baseline===null?'—':fmt(v.per_trace[i].delta_vs_baseline,5)}}<em v-if="v.per_trace[i].linear_likelihood_underflows">线性概率下溢，logL仍有限</em></small>
      </template>
     </td>
   </tr>
  </Table>
  <div class="boundary-note"><strong>累计logL只回答同一批观测下哪个固定模型更讲得通。</strong><p>不可解释版本不参与排序与差值；差值为负表示该轨迹上弱于基准。模型对比不做参数训练，也不构成真实故障或在线告警结论。</p></div>
  </section>
 </template>
 <Empty v-else :title="detail?.status==='failed'?'模型对比失败':'还没有完成的模型对比'" :help="detail?.error||'选择2–8个同码集合版本与1–30条轨迹排队，worker完成后在此展开。'"/>
</template>

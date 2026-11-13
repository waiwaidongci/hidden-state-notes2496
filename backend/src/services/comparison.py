import math
from sqlalchemy import select
from fastapi import HTTPException
from src.models import ModelProfile,ObservationTrace,ModelComparison,SequenceStudy
from src.utils.serialize import row
from .audit import record
from .hmm import infer_sequence,ImpossibleSequence
from .fingerprint import comparison_fingerprint

def compare_profiles(profiles,traces,baseline_profile_id):
 # 共用同一份冻结观测；候选只要求观测码集合相同，码顺序/状态数可不同。
 if not 2<=len(profiles)<=8:raise ValueError('一次对比2..8个模型版本')
 # 只要求观测码集合相同；码排列顺序与状态数允许不同，各版本按自己的码序映射观测。
 symbol_sets={frozenset(p['symbols']) for p in profiles}
 if len(symbol_sets)!=1:raise ValueError('候选版本的观测码集合不一致，无法共用同一批观测')
 ordered=sorted(traces,key=lambda t:t['reference'])
 trace_refs=[t['reference'] for t in ordered]
 if len(trace_refs)!=len(set(trace_refs)):raise ValueError('轨迹编号不能重复')
 for trace in ordered:
  if not 1<=len(trace['tokens'])<=200 or any(type(s) is not str or s not in profiles[0]['symbols'] for s in trace['tokens']):
   raise ValueError('轨迹须1..200个候选版本共用字母表内的观测码')
 if not any(p['id']==baseline_profile_id for p in profiles):raise ValueError('基准版本必须在候选版本内')
 entries=[]
 for profile in profiles:
  lookup={symbol:i for i,symbol in enumerate(profile['symbols'])}
  parameters=profile['parameters']
  per_trace=[];explainable=[]
  for trace in ordered:
   outcome={'id':trace['id'],'reference':trace['reference'],'token_count':len(trace['tokens'])}
   try:
    inferred=infer_sequence([lookup[s] for s in trace['tokens']],parameters['pi'],parameters['transition'],parameters['emission'])
   except ImpossibleSequence as error:
    # 单版本单轨迹零概率只把该格标为不可解释，其他版本/轨迹照常完成。
    outcome.update({'explainable':False,'log_likelihood':None,'linear_likelihood_underflows':None,'impossible_reason':str(error)})
   else:
    outcome.update({'explainable':True,'log_likelihood':inferred['log_likelihood'],'linear_likelihood_underflows':inferred['linear_likelihood_underflows'],'impossible_reason':None})
    explainable.append(inferred['log_likelihood'])
   per_trace.append(outcome)
  entries.append({'profile_id':profile['id'],'profile_name':profile['name'],'profile_version':profile['version'],'state_count':len(profile['states']),'trace_count':len(ordered),'explainable_count':len(explainable),'unexplainable_count':len(ordered)-len(explainable),'total_log_likelihood':math.fsum(explainable) if explainable else None,'per_trace':per_trace})
 by_id={e['profile_id']:e for e in entries}
 base_by_trace={o['id']:o for o in by_id[baseline_profile_id]['per_trace']}
 for entry in entries:
  for outcome in entry['per_trace']:
   base=base_by_trace[outcome['id']]
   if outcome['explainable'] and base['explainable']:
    outcome['delta_vs_baseline']=outcome['log_likelihood']-base['log_likelihood']
   else:
    # 基准或当前版本不可解释时差值无定义，不参与排序。
    outcome['delta_vs_baseline']=None
  if entry['total_log_likelihood'] is not None and by_id[baseline_profile_id]['total_log_likelihood'] is not None:
   entry['total_delta_vs_baseline']=entry['total_log_likelihood']-by_id[baseline_profile_id]['total_log_likelihood']
  else:
   entry['total_delta_vs_baseline']=None
 feasible=[e for e in entries if e['total_log_likelihood'] is not None]
 infeasible=[e for e in entries if e['total_log_likelihood'] is None]
 # 按累计对数似然降序；并列时按版本ID稳定排序，便于重复运行得到同一顺序。
 feasible.sort(key=lambda e:(-e['total_log_likelihood'],e['profile_id']))
 for rank,entry in enumerate(feasible,start=1):entry['rank']=rank
 for entry in infeasible:entry['rank']=None
 ranking=[{'rank':e['rank'],'profile_id':e['profile_id'],'profile_name':e['profile_name'],'profile_version':e['profile_version'],'state_count':e['state_count'],'total_log_likelihood':e['total_log_likelihood'],'explainable_count':e['explainable_count'],'unexplainable_count':e['unexplainable_count']} for e in feasible]+[{'rank':None,'profile_id':e['profile_id'],'profile_name':e['profile_name'],'profile_version':e['profile_version'],'state_count':e['state_count'],'total_log_likelihood':None,'explainable_count':0,'unexplainable_count':e['unexplainable_count']} for e in infeasible]
 # versions 与 ranking 严格同序，前端逐轨迹表头（ranking）与表体（versions）逐列对齐。
 ordered_entries={e['profile_id']:e for e in entries}
 versions=[ordered_entries[r['profile_id']] for r in ranking]
 return {'study_id':profiles[0]['study_id'],'baseline_profile_id':baseline_profile_id,'symbols':profiles[0]['symbols'],'trace_count':len(ordered),'token_count':sum(len(t['tokens']) for t in ordered),'trace_order':trace_refs,'ranking':ranking,'versions':versions,'fingerprint':comparison_fingerprint(profiles,ordered,baseline_profile_id),'interpretation':'共用同一批冻结观测的固定模型横向对比；累计logL仅对该版本可解释轨迹求和，零概率轨迹标为不可解释而非任务失败。线性概率下溢不误判为零概率。'}

def create_comparison(db,data,actor):
 study_id=data.study_id
 ids=data.profile_ids
 if not 2<=len(ids)<=8:raise HTTPException(422,'一次对比须选择2..8个模型版本')
 if len(ids)!=len(set(ids)):raise HTTPException(422,'模型版本不能重复')
 profiles=list(db.scalars(select(ModelProfile).where(ModelProfile.id.in_(ids)).order_by(ModelProfile.id)))
 if len(profiles)!=len(ids):raise HTTPException(422,'模型版本不存在')
 # 候选可来自不同研究：只要求观测码集合相同；码排列顺序与状态数允许不同。
 symbol_sets={frozenset(p.symbols) for p in profiles}
 if len(symbol_sets)!=1:raise HTTPException(422,'候选版本观测码集合不同，不能共用同一批观测')
 anchor=db.get(SequenceStudy,study_id)
 if not anchor:raise HTTPException(422,'对比研究不存在')
 if frozenset(anchor.symbols) not in symbol_sets:raise HTTPException(422,'候选版本观测码集合与对比研究不一致')
 if data.baseline_profile_id not in ids:raise HTTPException(422,'基准版本必须在候选版本内')
 trace_ids=data.trace_ids
 if len(trace_ids)!=len(set(trace_ids)):raise HTTPException(422,'轨迹ID不能重复')
 traces=list(db.scalars(select(ObservationTrace).where(ObservationTrace.id.in_(trace_ids),ObservationTrace.study_id==study_id).order_by(ObservationTrace.reference)))
 if len(traces)!=len(trace_ids):raise HTTPException(422,'轨迹不属于该研究或不存在')
 if db.scalar(select(ModelComparison).where(ModelComparison.name==data.name)):raise HTTPException(409,'对比名已存在')
 # 排队时冻结全部候选版本与观测；之后并发修订观测或重建版本都不改变已排队对比。
 comparison=ModelComparison(study_id=study_id,baseline_profile_id=data.baseline_profile_id,name=data.name,profile_snapshots=[row(p) for p in profiles],trace_snapshot=[row(t) for t in traces],created_by=actor)
 db.add(comparison);db.commit()
 try:
  from src.worker import compare_run
  compare_run.delay(comparison.id)
 except Exception:
  comparison.status='failed';comparison.error='队列不可用，请稍后重建';db.commit();raise HTTPException(503,comparison.error)
 record(db,actor,'comparison.queued',{'comparison_id':comparison.id,'profiles':len(profiles),'traces':len(traces)});return row(comparison)

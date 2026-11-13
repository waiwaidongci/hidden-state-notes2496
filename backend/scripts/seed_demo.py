import json
import numpy as np
from sqlalchemy import select,func
from src.config.database import Base,engine,SessionLocal
from src.models import User,SequenceStudy,ObservationTrace,ModelProfile,InferenceRun,ModelComparison,InterpretationNote
from src.utils.security import hash_password
from src.utils.serialize import row
from src.services.parameters import normalize_parameters
from src.services.analysis import analyze
from src.services.comparison import compare_profiles

def seed():
 Base.metadata.create_all(engine)
 with SessionLocal() as db:
  for role,name in [('admin','顾临 · 设备研究负责人'),('analyst','许汐 · 序列分析员'),('viewer','程沅 · 工况观察员')]:
   if not db.scalar(select(User).where(User.email==f'{role}@yanxi.demo')):db.add(User(email=f'{role}@yanxi.demo',name=name,role=role,password_hash=hash_password('Yanxi2026!')))
  db.commit();rng=np.random.default_rng(233);names=['YX-33A 常规观测序列','YX-33B 零转移假设序列','YX-33C 受限发射序列'];symbols=['A','B','C','D'];states=['稳态假设','缓变假设','跃迁假设'];models=[([.65,.25,.1],[[.85,.1,.05],[.08,.84,.08],[.12,.18,.7]],[[.7,.2,.08,.02],[.1,.65,.2,.05],[.04,.12,.24,.6]]),([1.,0.,0.],[[.8,.2,0.],[0.,.7,.3],[.4,0.,.6]],[[.5,.5,0.,0.],[0.,.5,.5,0.],[0.,0.,.4,.6]]),([1.,0.,0.],[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],[[.6,.4,0.,0.],[0.,0.,.5,.5],[.25,.25,.25,.25]])]
  for index,name in enumerate(names):
   study=db.scalar(select(SequenceStudy).where(SequenceStudy.name==name));params=normalize_parameters(*models[index])
   if not study:
    study=SequenceStudy(name=name,filename=f'yx-fixed-hmm-{index+1}-202611.json',description='独立合成观测轨迹，固定HMM假设，不含真实设备故障标签',symbols=symbols);db.add(study);db.flush()
    for i in range(80):
     state=int(rng.choice(3,p=params['pi']));tokens=[]
     for t in range(40):
      tokens.append(symbols[int(rng.choice(4,p=params['emission'][state]))]);state=int(rng.choice(3,p=params['transition'][state]))
     db.add(ObservationTrace(study_id=study.id,reference=f'YX{index+1}-T{i+1:03d}',tokens=tokens))
    db.commit()
   if not db.scalar(select(ModelProfile).where(ModelProfile.name==f'YX{index+1}-固定参数-v1')):db.add(ModelProfile(study_id=study.id,name=f'YX{index+1}-固定参数-v1',version='v1',states=states,symbols=symbols,parameters=params,normalization_max_delta=params['max_normalization_delta'],created_by='analyst@yanxi.demo'));db.commit()
  run=db.scalar(select(InferenceRun).where(InferenceRun.name=='A研究前20轨迹固定推断'))
  if not run:
   study=db.scalar(select(SequenceStudy).where(SequenceStudy.name==names[0]));profile=db.scalar(select(ModelProfile).where(ModelProfile.study_id==study.id));traces=[row(t) for t in db.scalars(select(ObservationTrace).where(ObservationTrace.study_id==study.id).order_by(ObservationTrace.reference).limit(20))];snapshot=row(profile);result=analyze(snapshot,traces);run=InferenceRun(study_id=study.id,profile_id=profile.id,name='A研究前20轨迹固定推断',profile_snapshot=snapshot,trace_snapshot=traces,status='completed',result=result,total_log_likelihood=result['total_log_likelihood'],created_by='analyst@yanxi.demo');db.add(run);db.commit()
  if not db.scalar(select(InterpretationNote).where(InterpretationNote.name=='A研究固定模型工况核对初稿')):db.add(InterpretationNote(run_id=run.id,name='A研究固定模型工况核对初稿',interpretation='隐态只由固定模型定义，边际最高态与联合MAP须分别解释。',next_step='回看观测码和设备记录，核对模型假设与观测含义；不把隐态当真实故障或在线告警。',result_snapshot=run.result,created_by='analyst@yanxi.demo'));db.commit()
  # 模型对比演示：同研究不同状态数版本、受限零概率版本，以及B研究中码集合相同但顺序不同的版本。
  study_a=db.scalar(select(SequenceStudy).where(SequenceStudy.name==names[0]));study_b=db.scalar(select(SequenceStudy).where(SequenceStudy.name==names[1]))
  extra=[
   ('YX1-固定参数-v2','v2',study_a.id,['稳态假设','跃迁假设'],symbols,([.7,.3],[[.8,.2],[.3,.7]],[[.6,.3,.08,.02],[.05,.15,.5,.3]])),
   ('YX1-固定参数-v3','v3',study_a.id,states,symbols,([1.,0.,0.],[[.8,.2,0.],[0.,.7,.3],[.4,0.,.6]],[[.7,.3,0.,0.],[.1,.3,.35,.25],[.05,.1,.25,.6]])),
   ('YX2-异码序对照版','v1-reorder',study_b.id,states,['D','C','B','A'],(models[0][0],models[0][1],[[.02,.08,.2,.7],[.05,.2,.65,.1],[.6,.24,.12,.04]])),
  ]
  for name,version,sid,st,sym,raw in extra:
   if not db.scalar(select(ModelProfile).where(ModelProfile.name==name)):
    params=normalize_parameters(*raw);assert len(st)==len(params['pi']),(name,len(st),len(params['pi']))
    db.add(ModelProfile(study_id=sid,name=name,version=version,states=st,symbols=sym,parameters=params,normalization_max_delta=params['max_normalization_delta'],created_by='analyst@yanxi.demo'));db.commit()
  if not db.scalar(select(ModelComparison).where(ModelComparison.name=='A研究前10轨迹四版本对比')):
   compare_profiles_names=['YX1-固定参数-v1','YX1-固定参数-v2','YX1-固定参数-v3','YX2-异码序对照版']
   cprofiles=[row(db.scalar(select(ModelProfile).where(ModelProfile.name==n))) for n in compare_profiles_names]
   ctraces=[row(t) for t in db.scalars(select(ObservationTrace).where(ObservationTrace.study_id==study_a.id).order_by(ObservationTrace.reference).limit(10))]
   baseline=cprofiles[0]['id'];cresult=compare_profiles(cprofiles,ctraces,baseline)
   db.add(ModelComparison(study_id=study_a.id,baseline_profile_id=baseline,name='A研究前10轨迹四版本对比',profile_snapshots=cprofiles,trace_snapshot=ctraces,status='completed',result=cresult,created_by='analyst@yanxi.demo'));db.commit()
  counts={m.__tablename__:db.scalar(select(func.count()).select_from(m)) for m in [User,SequenceStudy,ObservationTrace,ModelProfile,InferenceRun,ModelComparison,InterpretationNote]};print(json.dumps(counts));return counts
if __name__=='__main__':seed()

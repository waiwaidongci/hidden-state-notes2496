import json,hashlib
VERSION='fixed-hmm-log-fb-viterbi-v1'
def fingerprint(profile,traces):
 payload={'version':VERSION,'profile':profile,'traces':sorted(traces,key=lambda t:t['reference'])}
 return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def comparison_fingerprint(profiles,traces,baseline_profile_id):
 payload={'version':VERSION,'kind':'model-comparison','baseline_profile_id':baseline_profile_id,'profiles':sorted(profiles,key=lambda p:p['id']),'traces':sorted(traces,key=lambda t:t['reference'])}
 return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

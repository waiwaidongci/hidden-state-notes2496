from pydantic import BaseModel,Field
from typing import Annotated
Id=Annotated[int,Field(gt=0,strict=True)]
class ComparisonInput(BaseModel):
 study_id:Id
 name:str=Field(min_length=2,max_length=180)
 baseline_profile_id:Id
 profile_ids:list[Id]=Field(min_length=2,max_length=8)
 trace_ids:list[Id]=Field(min_length=1,max_length=30)

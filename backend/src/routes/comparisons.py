from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import get_db
from src.controllers.dependencies import current_user,writers
from src.models import ModelComparison
from src.schemas.comparison import ComparisonInput
from src.services.comparison import create_comparison
from src.utils.serialize import row
router=APIRouter()
@router.get('/comparisons')
def comparisons(db:Session=Depends(get_db),user=Depends(current_user)):return [row(c) for c in db.scalars(select(ModelComparison).order_by(ModelComparison.id.desc()))]
@router.get('/comparisons/{id}')
def one(id:int,db:Session=Depends(get_db),user=Depends(current_user)):
 c=db.get(ModelComparison,id)
 if not c:raise HTTPException(404,'模型对比不存在')
 return row(c)
@router.post('/comparisons')
def create(data:ComparisonInput,db:Session=Depends(get_db),user=Depends(writers)):return create_comparison(db,data,user.email)

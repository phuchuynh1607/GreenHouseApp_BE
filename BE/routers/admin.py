from fastapi import APIRouter,HTTPException,Path
from BE.models.users_model import Users, LoginHistory
from starlette import status
from .auth import user_dependency,db_dependency,UserResponse
from ..schemas.login_history_schema import LoginHistoryResponse
from typing import List
router=APIRouter(prefix='/admin',
    tags=['admin'])



@router.get("/users/",status_code=status.HTTP_200_OK,response_model=list[UserResponse])
async def read_all_user(user:user_dependency,db:db_dependency):
    if user is None or user.get('user_role')!='admin':
        raise HTTPException(status_code=403, detail='You do not have permission to access this.')
    return db.query(Users).filter(Users.role == 'user').all()

@router.get("/user/{user_id}",status_code=status.HTTP_200_OK,response_model=UserResponse)
async def read_user(user:user_dependency,db:db_dependency,user_id:int =Path(gt=0)):
    if user is None or user.get('user_role')!='admin':
        raise HTTPException(status_code=403,detail='You do not have permission to access this.')
    return db.query(Users).filter(Users.id == user_id).first()

@router.delete("/user/{user_id}",status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user:user_dependency,db:db_dependency,user_id:int =Path(gt=0)):
    if user is None or user.get('user_role')!='admin':
        raise HTTPException(status_code=403,detail='You do not have permission to access this.')

    if user_id == user.get('id'):
        raise HTTPException(status_code=400,detail='Cannot delete admin.')

    user_model=db.query(Users).filter(Users.id == user_id).first()

    if user_model is None:
        raise HTTPException(status_code=404,detail='User not found.')
    db.query(Users).filter(Users.id == user_id).delete()
    db.commit()


@router.get("/login-history/{user_id}", response_model=List[LoginHistoryResponse])
async def get_user_login_history_by_admin(
        user: user_dependency,
        db: db_dependency,
        user_id: int = Path(gt=0)
):
    if user is None or user.get('user_role') != 'admin':
        raise HTTPException(status_code=403, detail='Admin access required')

    history = db.query(LoginHistory) \
        .filter(LoginHistory.user_id == user_id) \
        .order_by(LoginHistory.login_time.desc()) \
        .limit(50) \
        .all()

    return history
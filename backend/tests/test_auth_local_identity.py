"""Existing local-domain identities can sign in without relaxing registration."""
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from app import models as m
from app.core.security import hash_password
from app.schemas.auth import RegisterRequest
from test_core_hr import db, client


def test_existing_local_identity_login_and_me(db,client):
    email=f'{uuid4().hex}@fusionhcm.local'
    password=uuid4().hex
    user=m.User(email=email,first_name='Anusha',last_name='Reddy',password_hash=hash_password(password))
    db.add(user);db.flush()
    db.add(m.UserRole(user_id=user.id,role_id=db.scalar(select(m.Role.id).where(m.Role.name=='EMPLOYEE'))));db.commit()
    response=client.post('/auth/login',json={'email':email,'password':password})
    assert response.status_code==200
    me=client.get('/auth/me',headers={'Authorization':'Bearer '+response.json()['access_token']})
    assert me.status_code==200 and me.json()['email']==email
    assert client.post('/auth/login',json={'email':email,'password':'incorrect'}).status_code==401
    with pytest.raises(ValidationError):
        RegisterRequest(email=email,password=password,first_name='Anusha',last_name='Reddy')

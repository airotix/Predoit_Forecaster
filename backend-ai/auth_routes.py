"""Authentication routes and the request gate used by the access-control middleware.

`authorize(request)` returns None while authentication is off (existing local-only rules then
apply), True when the request may proceed, or a JSON denial response. Role requirements come
from rbac.required_role, so routes need no per-endpoint dependencies.
"""
import datetime as dt
import re

from fastapi import Body, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

import access_settings as settings
import local_auth
from auth import AuthError, dev_user, validate_token
from rbac import VALID_ROLES, has_min_role, required_role
from users_store import (count_users, create_user, ensure_users_table, get_user_by_email, list_users,
                         touch_user_login, update_user_role)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MIN_PASSWORD_LEN = 8
EVENT_PATH = '/api/events'


def _denial(status, detail):
    headers = {'WWW-Authenticate': 'Bearer'} if status == 401 else None
    return JSONResponse({'detail': detail}, status_code=status, headers=headers)


def _token(request):
    header = request.headers.get('authorization', '')
    if header.lower().startswith('bearer ') and header[7:].strip():
        return header[7:].strip()
    # EventSource cannot set headers, so the SSE stream alone accepts a query token.
    if request.url.path.rstrip('/') == EVENT_PATH:
        return request.query_params.get('access_token') or None
    return None


def authorize(request):
    if not settings.auth_is_active():
        return None
    minimum = required_role(request.method, request.url.path)
    if request.method == 'OPTIONS' or minimum is None:
        return True
    token = _token(request)
    if not token:
        return _denial(401, 'Authentication required.')
    try:
        user = validate_token(token)
    except AuthError as error:
        return _denial(error.status, error.detail)
    if not has_min_role(user.roles, minimum):
        return _denial(403, f'Requires {minimum} role or higher.')
    request.state.user = user
    return True


def current_user(request):
    return getattr(request.state, 'user', None) or dev_user()


def _public(user):
    return {'id': user['id'], 'email': user['email'], 'name': user.get('name') or '', 'role': user['role'],
            'status': user.get('status') or 'active'}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ''


class LoginRequest(BaseModel):
    email: str
    password: str


class RoleUpdateRequest(BaseModel):
    email: str
    role: str


def ensure_schema(conn):
    ensure_users_table(conn)
    conn.commit()


def install(app, connection):
    def session(user):
        return {'token': local_auth.issue_token(user), 'user': _public(user),
                'expiresInHours': settings.AUTH_TOKEN_TTL_HOURS}

    @app.get('/api/auth/config')
    def auth_config():
        """Public: tells the frontend which sign-in methods are available."""
        return {'authEnabled': settings.AUTH_ENABLED, 'authActive': settings.auth_is_active(),
                'ssoEnabled': settings.SSO_ENABLED, 'passwordEnabled': True,
                'signupAllowed': settings.AUTH_ALLOW_SIGNUP, 'devMode': not settings.auth_is_active(),
                'devRole': settings.AUTH_DEV_ROLE, 'roles': ['owner', 'admin', 'manager', 'worker']}

    @app.post('/api/auth/signup')
    def signup(payload: SignupRequest):
        """Register a local account. The first account becomes owner; later ones are view-only workers."""
        if not settings.AUTH_ALLOW_SIGNUP:
            raise HTTPException(403, 'Self sign-up is disabled. Ask an administrator to create your account.')
        email = (payload.email or '').strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(422, 'Please enter a valid email address.')
        if len(payload.password or '') < MIN_PASSWORD_LEN:
            raise HTTPException(422, f'Password must be at least {MIN_PASSWORD_LEN} characters.')
        conn = connection()
        try:
            ensure_users_table(conn)
            if get_user_by_email(conn, email) is not None:
                raise HTTPException(409, 'An account with this email already exists.')
            user = create_user(conn, email=email, name=payload.name or email.split('@')[0],
                               password_hash=local_auth.hash_password(payload.password),
                               role='owner' if count_users(conn) == 0 else 'worker', status='active', now=_now())
        finally:
            conn.close()
        return session(user)

    @app.post('/api/auth/login')
    def login(payload: LoginRequest):
        email = (payload.email or '').strip().lower()
        conn = connection()
        try:
            ensure_users_table(conn)
            user = get_user_by_email(conn, email)
            if user is None or not local_auth.verify_password(payload.password or '', user['password_hash']):
                raise HTTPException(401, 'Incorrect email or password.')
            if (user.get('status') or 'active') != 'active':
                raise HTTPException(403, 'This account is not active. Contact an administrator.')
            touch_user_login(conn, email, _now())
        finally:
            conn.close()
        return session(user)

    @app.get('/api/auth/me')
    def me(request: Request):
        user = current_user(request)
        return {'id': user.sub, 'email': user.email, 'name': user.display_name, 'role': user.primary_role,
                'roles': list(user.roles)}

    @app.get('/api/auth/users')
    def users():
        """Local accounts (admin/owner). SSO-only users are not listed."""
        conn = connection()
        try:
            ensure_users_table(conn)
            return {'users': list_users(conn)}
        finally:
            conn.close()

    @app.put('/api/auth/users/role')
    def change_role(request: Request, payload: RoleUpdateRequest = Body(...)):
        if payload.role not in VALID_ROLES:
            raise HTTPException(422, 'Invalid role.')
        target = (payload.email or '').strip().lower()
        if target and target == (current_user(request).email or '').strip().lower():
            raise HTTPException(400, 'You cannot change your own role.')
        conn = connection()
        try:
            ensure_users_table(conn)
            if get_user_by_email(conn, target) is None:
                raise HTTPException(404, 'User not found.')
            return {'user': _public(update_user_role(conn, target, payload.role, _now()))}
        finally:
            conn.close()

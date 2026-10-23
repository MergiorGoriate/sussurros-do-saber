"""Signed, expiring plan intent across the existing account flows; never a URL."""
from flask import current_app, request, session, url_for
from itsdangerous import URLSafeTimedSerializer, BadData
from werkzeug.exceptions import HTTPException


def serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='premium-plan-return-v1')


def remember_plan(ident):
    token=serializer().dumps(ident)
    session['premium_return']=token
    return token


def selected_plan():
    form_token=None
    if request.endpoint in {'submissions.login','submissions.register','submissions.verify','submissions.verify_notice','submissions.forgot_password','submissions.reset_password','reader.login','google_auth.login'}:
        try:form_token=request.form.get('premium_return')
        except HTTPException:pass  # Error pages must not parse an already rejected request body.
    token=form_token or request.args.get('premium_return') or session.get('premium_return')
    try:
        if not isinstance(token,str) or len(token)>512:raise ValueError()
        ident=serializer().loads(token,max_age=86400)
        if type(ident) is not int or not 0<ident<=2147483647:raise ValueError()
    except (BadData,ValueError,TypeError):
        session.pop('premium_return',None)
        return None
    session['premium_return']=token
    return ident


def auth_url(endpoint, **values):
    if selected_plan():values['premium_return']=session['premium_return']
    return url_for(endpoint,**values)


def preserve_intent():
    return session.get('premium_return') if selected_plan() else None


def resume_url(account, token):
    if not token:return None
    session['premium_return']=token
    ident=selected_plan()
    if not ident:return None
    if not account.verified:return auth_url('submissions.verify_notice')
    return url_for('billing.checkout',ident=ident)

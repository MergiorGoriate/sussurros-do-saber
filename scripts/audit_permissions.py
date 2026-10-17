"""Read-only catalogue/mandate audit. Does not import Flask or run schema/seed code.
Run in the application container: python scripts/audit_permissions.py
Only IDs, role configuration and access prerequisites are exported, no credentials.
"""
import ast
import json
import os
import sys
from datetime import date
from pathlib import Path
from sqlalchemy import MetaData, Table, create_engine, select, text


def catalog():
    wanted={'PERMISSIONS','DEFAULT_ROLES','JOURNAL_PERMISSIONS'}
    values={}
    for node in ast.parse((Path(__file__).resolve().parents[1]/'governance.py').read_text()).body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in wanted:
            values[node.targets[0].id]=ast.literal_eval(node.value)
    return values


def inspect_database(url):
    definitions=catalog();engine=create_engine(url.replace('postgres://','postgresql://',1))
    with engine.connect() as conn:
        if engine.dialect.name=='postgresql':conn.execute(text('SET TRANSACTION READ ONLY'))
        elif engine.dialect.name=='sqlite':conn.execute(text('PRAGMA query_only = ON'))
        else:raise ValueError('Use PostgreSQL ou SQLite para esta auditoria.')
        meta=MetaData()
        tables={name:Table(name,meta,autoload_with=conn) for name in ['team_role','team_member','team_appointment','admin_user']}
        roles=[dict(r) for r in conn.execute(select(tables['team_role'])).mappings()]
        role_map={r['id']:r for r in roles}
        m=tables['team_member'];a=tables['admin_user'];t=tables['team_appointment']
        members=conn.execute(select(m.c.id,m.c.admin_id,m.c.author_id,m.c.status,m.c.accepted_at,m.c.removed_at)).mappings().all()
        accounts={r['id']:r for r in conn.execute(select(a.c.id,a.c.active,a.c.is_superadmin,a.c.governance_managed)).mappings()}
        appointments=[dict(r) for r in conn.execute(select(t)).mappings()]
        results=[];today=date.today()
        for member in members:
            account=accounts.get(member['admin_id'])
            ready=bool(not member['removed_at'] and member['status']=='active' and member['accepted_at'] and account and account['active'])
            valid=[x for x in appointments if x['member_id']==member['id'] and x['active'] and x['starts_on']<=today and (not x['ends_on'] or x['ends_on']>=today)]
            general=set();journals={};blocked=[]
            for mandate in valid:
                for permission in role_map[mandate['role_id']]['permissions']:
                    if permission not in definitions['PERMISSIONS']:
                        blocked.append({'permission':permission,'reason':'identificador desconhecido','appointment_id':mandate['id']})
                    elif mandate['journal_id'] is None:
                        if ready:general.add(permission)
                    elif permission in definitions['JOURNAL_PERMISSIONS']:
                        if ready:journals.setdefault(str(mandate['journal_id']),set()).add(permission)
                    else:blocked.append({'permission':permission,'reason':'exige mandato geral','appointment_id':mandate['id']})
            results.append({'member_id':member['id'],'admin_id':member['admin_id'],'author_id':member['author_id'],
                'status':member['status'],'removed':bool(member['removed_at']),'accepted':bool(member['accepted_at']),'account_active':bool(account and account['active']),
                'valid_appointments':[x['id'] for x in valid],'effective_general':sorted(general),
                'effective_journals':{key:sorted(value) for key,value in journals.items()},'blocked':blocked})
        # No commit: read-only transaction is rolled back on closing the connection.
    engine.dispose()
    return {'permissions':definitions['PERMISSIONS'],'roles':roles,'members':results,
            'reserved_to_founder':['account_linking','role_catalogue_changes','appointment_creation','appointment_termination'],
            'notes':['General grants also apply to every journal. Scoped grants never broaden other mandates.',
                     'Manuscript conflicts, assignment, phase and version are checked again on each resource route.',
                     'Founder and historical unmanaged accounts follow the compatibility rules in governance.py.']}


if __name__=='__main__':
    try:
        print(json.dumps(inspect_database(os.environ['DATABASE_URL']),ensure_ascii=False,indent=2,default=str))
    except Exception:
        sys.exit('Não foi possível ler a configuração. Confirme DATABASE_URL e a migração 20261008_03; nenhum dado foi alterado.')

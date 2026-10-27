"""Exercise collector.ttl :prepare_privilege from the requested v0.1.1 policy.

The actual TTL procedure is executed by the limited source-driven Model.
Send operations are recorded in memory; receive events are scenario fixtures,
matched against the procedure's actual regexes with real Oniguruma. This is
NOT a Windows/Tera Term, DDE, SSH, Telnet or Cisco integration test.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from test_collector_procedures import Model


# Deliberately different, fictitious values make cross-method leakage visible.
SSH_ENABLE = b'FAKE_SSH_ENABLE_ONLY'
TELNET_ENABLE = b'FAKE_TELNET_ENABLE_ONLY'


@dataclass(frozen=True)
class Case:
    name: str
    auth_index: int
    initial_prompt: bytes
    receive: tuple[bytes | None,...]
    expected_send: tuple[bytes,...]
    success: bool
    status: bytes | None = None
    passwords: tuple[bytes,bytes] = (SSH_ENABLE,TELNET_ENABLE)


def policy_cases():
    yield Case('tacacs_privileged',0,b'sw-01#',(),(),True)
    yield Case('tacacs_unprivileged_no_enable',0,b'sw-01>',(),(),False,b'TACACS_NOT_PRIVILEGED')
    yield Case('tacacs_config_prompt_rejected',0,b'sw-01(config)#',(),(),False)
    yield Case('negative_auth_method_rejected',-1,b'sw-01#',(),(),False,b'UNEXPECTED_AUTH_METHOD')
    yield Case('unknown_auth_method_rejected',3,b'sw-01>',(),(),False,b'UNEXPECTED_AUTH_METHOD')
    for method,label,own in ((1,'common_ssh',SSH_ENABLE),(2,'telnet',TELNET_ENABLE)):
        prefix=label+'_'
        yield Case(prefix+'already_privileged_no_enable',method,b'sw-01#',(),(),True)
        yield Case(prefix+'initial_config_rejected',method,b'sw-01(config)#',(),(),False)
        yield Case(prefix+'password_enable_success',method,b'sw-01>',
                   (b'Password:',b'sw-01#'),(b'enable',own),True)
        yield Case(prefix+'passwordless_enable_success',method,b'sw-01>',
                   (b'sw-01#',),(b'enable',),True)
        yield Case(prefix+'enable_still_unprivileged',method,b'sw-01>',
                   (b'sw-01>',),(b'enable',),False)
        missing=(b'',TELNET_ENABLE) if method==1 else (SSH_ENABLE,b'')
        yield Case(prefix+'missing_own_password_never_uses_other',method,b'sw-01>',
                   (b'Password:',),(b'enable',),False,passwords=missing)
        yield Case(prefix+'repeated_password_stops',method,b'sw-01>',
                   (b'Password:',b'Password:'),(b'enable',own),False)
        yield Case(prefix+'authentication_rejected',method,b'sw-01>',
                   (b'Password:',b'% Access denied'),(b'enable',own),False)
        yield Case(prefix+'timeout_before_password',method,b'sw-01>',
                   (None,),(b'enable',),False)
        yield Case(prefix+'timeout_after_password',method,b'sw-01>',
                   (b'Password:',None),(b'enable',own),False)
        yield Case(prefix+'config_prompt_before_password_rejected',method,b'sw-01>',
                   (b'sw-01(config)#',),(b'enable',),False)
        yield Case(prefix+'config_prompt_after_password_rejected',method,b'sw-01>',
                   (b'Password:',b'sw-01(config)#'),(b'enable',own),False)
        yield Case(prefix+'changed_host_before_password_rejected',method,b'sw-01>',
                   (b'other-sw#',),(b'enable',),False)
        yield Case(prefix+'changed_host_after_password_rejected',method,b'sw-01>',
                   (b'Password:',b'other-sw#'),(b'enable',own),False)
        yield Case(prefix+'username_prompt_rejected',method,b'sw-01>',
                   (b'Username:',),(b'enable',),False)
        yield Case(prefix+'command_denied',method,b'sw-01>',
                   (b'% Command authorization failed.',),(b'enable',),False)


def execute_case(macro:Path,mode:int,case:Case):
    m=Model(macro)
    m.v.update(auth_index=case.auth_index,output_mode=mode,
               learned_prompt=case.initial_prompt,enable_pass=list(case.passwords),
               login_seconds=30,mtimeout=0)
    m.receive_events=list(case.receive)
    m.run('prepare_privilege')
    assert bool(m.v['privilege_ok'])==case.success,(
        'privilege result',m.v['privilege_ok'],m.v.get('privilege_status'))
    assert tuple(m.sent)==case.expected_send,('unexpected send sequence',m.sent,case.expected_send)
    assert m.sent.count(b'enable')<=1,'enable retried'
    assert not m.receive_events,('unconsumed expected receive events',m.receive_events)
    if case.status is not None:
        assert m.v['privilege_status']==case.status,('wrong failure reason',m.v['privilege_status'])
    if case.success:
        assert m.v['privilege_status']==b'READY'
        assert m.v['learned_prompt']==b'sw-01#'
        pattern=m.v['prompt_pattern'].decode('utf-8')
        assert m.onig.search(pattern,'sw-01#') is not None
        assert m.onig.search(pattern,'sw-01#show version') is None
        assert m.onig.search(pattern,'other-sw#') is None
    else:
        assert m.v['privilege_status']!=b'READY'
    if case.auth_index==0:
        assert not m.sent,'TACACS must never send enable or an enable password'
    elif case.auth_index==1:
        assert TELNET_ENABLE not in m.sent,'common SSH sent Telnet enable password'
    else:
        assert SSH_ENABLE not in m.sent,'Telnet sent common SSH enable password'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('macro',type=Path)
    a=p.parse_args()
    passed=[];failed=[]
    scenarios=list(policy_cases())
    for mode in (0,1,2):
        for case in scenarios:
            name=f'mode{mode}_{case.name}'
            try:
                execute_case(a.macro,mode,case)
                passed.append(name)
            except Exception as e:
                failed.append({'case':name,'error':repr(e)})
    report={'source_privilege_policy_cases':len(passed)+len(failed),
            'scenarios_per_output_mode':len(scenarios),'output_modes':[0,1,2],
            'passed':len(passed),'failures':failed,
            'limits':'Source-driven subset simulation with explicit receive fixtures; NOT native Tera Term or device execution.'}
    print(json.dumps(report,indent=2,ensure_ascii=False))
    raise SystemExit(bool(failed))


if __name__=='__main__':main()
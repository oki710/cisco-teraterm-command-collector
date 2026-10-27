"""Requirement-based samples executed against regex constants in collector.ttl.

This uses the real Oniguruma library, not a Python translation. It is not a
Windows/Tera Term session test and does not model network chunk timing.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from check_ttl import Checker,known_words,tokenize
from onig_check import Onig


CASES={
 'host_re':([
     'router01','switch-2960.example.test','192.0.2.10','sw_01','r'+'a'*252,
 ],[
     '', '-bad','router /ssh','router;comment','router:22','[2001:db8::1]',
     '../router','r\\x','r\nshow version','r'+'a'*253,
 ]),
 'command_re':([
     'show version','SHOW clock','show ip route | include 192.0.2.',
     'show interface GigabitEthernet1/0/1','show running-config',
 ],[
     '', 'show', 'show ', 'sh ver', 'configure terminal','reload',
     'show version\nreload','show clock\rreload','show\tversion',
     'show version\x1b',
 ]),
 'write_pipe_re':([
     'show version | redirect tftp://host/file',
     'show version|r tftp://host/file','show version | red tftp://host/file',
     'show version | REDIRECT tftp://host/file',
     'show version | append tftp://host/file','show version|ap tftp://host/file',
     'show version | a tftp://host/file','show version | tee flash:test',
     'show version | te flash:test','show version | t flash:test',
 ],[
     'show version','show running-config | include append',
     'show running-config | include redirect','show ip route | begin 192.0.2.',
     'show interfaces | exclude drops','show logging | include ERROR',
 ]),
 'prompt_re':([
     'router#','sw-01>','SW01# ','sw.domain.example#\t','sw01(config)#',
     'RP/0/CPU0:router#',
 ],[
     '', '#','>','Cisco IOS Software, Version 17.9','sw01#show version',
     'some line containing #','banner # fragment','sw01# trailing text',
 ]),
 'password_re':(['Password:','password: ','PASSWORD:\t'],[
     'password encryption enabled','Password: wrong','username:',
 ]),
 'username_re':(['Username:','login: ','User Name:'],[
     'login authentication default','Password:','Username: admin',
 ]),
 'login_error_re':([
     '% Authentication failed','Login invalid','Access denied',
     '% Bad passwords','Authentication failure',
 ],['router#','User Access Verification','Password:']),
 'cli_error_re':([
     "% Invalid input detected at '^' marker.",'% Incomplete command.',
     '% Ambiguous command: "show i"','% Authorization failed.',
     '% Command authorization failed.','%Error opening tftp://host/file (Timed out)',
     'Error opening flash:file','TFTP: Error code 2 received',
     'Access violation','Permission denied',
 ],[
     '0 input errors, 0 CRC','Last clearing of counters never',
     'Authorization enabled','router#',
 ]),
 'pager_re':([' --More-- ','<--- More --->'],['more information available','router#']),
 'interactive_re':([
     '[confirm]','Continue? [yes/no]','Proceed? [yes/no/cancel]',
     'Destination filename [config.txt]?', 'Address or name of remote host []?',
 ],['0 errors','router#']),
}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('macro',type=Path)
    a=p.parse_args()
    checker=Checker(known_words())
    structure=checker.check(a.macro)
    patterns=checker.constants
    onig=Onig()
    failures=[]
    total=0
    for name,(accept,reject) in CASES.items():
        if name not in patterns:
            failures.append({'pattern':name,'error':'constant missing'})
            continue
        pattern=patterns[name]
        for expected,samples in ((True,accept),(False,reject)):
            for sample in samples:
                total+=1
                try:
                    actual=onig.search(pattern,sample) is not None
                    if actual!=expected:
                        failures.append({'pattern':name,'sample':sample,'expected':expected,'actual':actual})
                except Exception as e:
                    failures.append({'pattern':name,'error':str(e)})
    # Native strmatch/strreplace literal regexes outside named constants also compile.
    inline_count=0
    for n,line in enumerate(a.macro.read_text(encoding='utf-8-sig').splitlines(),1):
        try:
            ts=tokenize(line)
        except ValueError:
            continue
        if not ts:
            continue
        pattern_index={'strmatch':2,'strreplace':3}.get(ts[0].value)
        if pattern_index is not None and len(ts)>pattern_index and ts[pattern_index].kind=='string':
            try:
                onig.search(ts[pattern_index].value,'')
                inline_count+=1
            except Exception as e:
                failures.append({'line':n,'error':str(e)})
    report={'engine':'Oniguruma '+onig.version,'cases':total,'inline_regex_compiles':inline_count,
            'failures':failures,'limits':'Regex matching only; no native macro/session/device run.'}
    print(json.dumps(report,indent=2,ensure_ascii=False))
    raise SystemExit(bool(failures))


if __name__=='__main__':
    main()

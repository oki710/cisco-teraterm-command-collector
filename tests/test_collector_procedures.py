"""Run selected actual TTL procedures in a deliberately limited test model.

This is NOT the Tera Term interpreter. The model covers the documented byte
string operations, arrays, loops and file-read behavior used by read_input,
quote_argument, check_credential, check_tacacs_limit and check_ssh_pair.
For prepare_privilege, sendln is recorded
in memory and waitregex consumes explicitly supplied receive events using the
real Oniguruma engine. Network timing, DDE, GUI and logging are absent.
Unknown operations fail loudly; they are never silently skipped.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from check_ttl import tokenize,PRECEDENCE,Checker,known_words
from onig_check import Onig


class Model:
    def __init__(self,path):
        self.lines=path.read_text(encoding='utf-8-sig').splitlines()
        self.tokens=[tokenize(x) for x in self.lines]
        self.labels={x[1].value:i for i,x in enumerate(self.tokens) if x and x[0].value==':'}
        self.ends={}
        self.branches={}
        self.branch_owner={}
        stack=[]
        for i,ts in enumerate(self.tokens):
            if not ts: continue
            h=ts[0].value
            if h=='if' and ts[-1].value=='then':
                stack.append(('if',i,[i]))
            elif h in ('else','elseif'):
                if stack[-1][0]!='if': raise ValueError('model block mismatch')
                stack[-1][2].append(i)
            elif h in ('while','for'):
                stack.append((h,i,[]))
            elif h in ('endif','endwhile','next'):
                k,start,branches=stack.pop()
                self.ends[start]=i
                self.ends[i]=start
                if k=='if':
                    for n,b in enumerate(branches):
                        self.branches[b]=(branches[n+1] if n+1<len(branches) else i,i)
                        self.branch_owner[b]=start
        if stack: raise ValueError('unbalanced source')
        checker=Checker(known_words())
        checker.check(path)
        self.v={k:s.encode('utf-8') for k,s in checker.constants.items()}
        self.v.update(result=0,host_count=0,command_count=0,max_hosts=1000,max_commands=256,
                      hosts=[b'']*1000,commands=[b'']*256,slugs=[b'']*256)
        self.files={}
        self.fd={}
        self.onig=Onig()
        self.loop=[]
        self.steps=0
        self.if_taken={}
        self.receive_events=[]
        self.sent=[]
        self.flush_count=0

    def literal(self,t,line):
        s=line[t.start:t.end]
        out=b''
        i=0
        while i<len(s):
            c=s[i];i+=1
            if c in "\"'":
                e=s.index(c,i)
                out+=s[i:e].encode('utf-8');i=e+1
            elif c=='#':
                e=i
                if s[i]=='$':
                    e+=1
                    while e<len(s) and s[e] in '0123456789abcdefABCDEF':e+=1
                    out+=bytes([int(s[i+1:e],16)])
                else:
                    while e<len(s) and s[e].isdigit():e+=1
                    out+=bytes([int(s[i:e])])
                i=e
            else: raise ValueError('unexpected literal syntax')
        return out[:511]

    def expr(self,ts,i,line,minimum=0):
        t=ts[i];i+=1
        if t.kind=='string':
            val=self.literal(t,line)
        elif t.value in ('+','-','~','!','not'):
            val,i=self.expr(ts,i,line,11)
            val={'+' :lambda x:x,'-':lambda x:-x,'~':lambda x:~x,
                 'not':lambda x:~x,'!':lambda x:int(not x)}[t.value](val)
        elif t.value=='(':
            val,i=self.expr(ts,i,line)
            if ts[i].value!=')':raise ValueError('missing )')
            i+=1
        elif t.kind=='number':
            val=int(t.value[1:],16) if t.value.startswith('$') else int(t.value)
        elif t.kind=='name':
            val=self.v[t.value]
            if i<len(ts) and ts[i].value=='[':
                index,i=self.expr(ts,i+1,line)
                if ts[i].value!=']':raise ValueError('missing ]')
                i+=1
                if not 0<=index<len(val):raise IndexError(f'{t.value}[{index}]')
                val=val[index]
        else:raise ValueError('bad model expression '+t.value)
        while i<len(ts) and ts[i].value in PRECEDENCE and PRECEDENCE[ts[i].value]>=minimum:
            op=ts[i].value
            right,i=self.expr(ts,i+1,line,PRECEDENCE[op]+1)
            if isinstance(val,bytes) or isinstance(right,bytes):raise TypeError('numeric operands needed')
            f={'+':lambda a,b:a+b,'-':lambda a,b:a-b,'*':lambda a,b:a*b,'/':lambda a,b:a//b,
               '%':lambda a,b:a%b,'=':lambda a,b:int(a==b),'==':lambda a,b:int(a==b),
               '!=':lambda a,b:int(a!=b),'<>':lambda a,b:int(a!=b),'<':lambda a,b:int(a<b),
               '>':lambda a,b:int(a>b),'<=':lambda a,b:int(a<=b),'>=':lambda a,b:int(a>=b),
               'and':lambda a,b:a&b,'&':lambda a,b:a&b,'or':lambda a,b:a|b,'|':lambda a,b:a|b,
               'xor':lambda a,b:a^b,'^':lambda a,b:a^b,'&&':lambda a,b:int(bool(a) and bool(b)),
               '||':lambda a,b:int(bool(a) or bool(b)),'<<':lambda a,b:a<<b,'>>':lambda a,b:a>>b}
            val=f[op](val,right)
        return val,i

    def arguments(self,ts,i,line):
        aa=[]
        while i<len(ts):
            val,j=self.expr(ts,i,line)
            aa.append((ts[i:j],val));i=j
        return aa

    def reference(self,ts,i,line):
        name=ts[i].value;i+=1
        index=None
        if i<len(ts) and ts[i].value=='[':
            index,i=self.expr(ts,i+1,line)
            if ts[i].value!=']':raise ValueError('missing ]')
            i+=1
        return (name,index),i

    def put(self,ref,value):
        if isinstance(value,bytes):value=value.split(b'\0',1)[0][:511]
        name,index=ref
        if index is None:self.v[name]=value
        else:
            if not 0<=index<len(self.v[name]):raise IndexError(f'{name}[{index}]')
            self.v[name][index]=value

    def run(self,label):
        self.ip=self.labels[label]+1
        self.loop=[]
        self.if_taken={}
        while self.ip<len(self.lines):
            self.steps+=1
            if self.steps>500000:raise RuntimeError('step bound exceeded')
            i=self.ip;self.ip+=1
            self.step(self.tokens[i],self.lines[i],i)
            if self.ip<0:return
        raise RuntimeError('fell off source')

    def step(self,ts,line,source_index):
        if not ts:return
        h=ts[0].value
        if h==':':return
        # Assignment is recognized before command handling.
        ref,j=self.reference(ts,0,line)
        if j<len(ts) and ts[j].value=='=':
            val,k=self.expr(ts,j+1,line)
            if k!=len(ts):raise ValueError('trailing assignment')
            self.put(ref,val);return
        if h=='return':self.ip=-1;return
        if h in ('if','elseif'):
            if h=='elseif' and self.if_taken.get(self.branch_owner[source_index],False):
                self.ip=self.branches[source_index][1]+1
                del self.if_taken[self.branch_owner[source_index]]
                return
            val,j=self.expr(ts,1,line)
            if ts[j].value=='then':
                self.if_taken[self.branch_owner[source_index]]=bool(val)
                if not val:
                    nxt,end=self.branches[source_index]
                    self.ip=nxt
            elif val:self.step(ts[j:],line,source_index)
            return
        if h=='else':
            owner=self.branch_owner[source_index]
            if self.if_taken.get(owner,False):
                self.ip=self.branches[source_index][1]+1
                del self.if_taken[owner]
            else:self.if_taken[owner]=True
            return
        if h=='endif':
            self.if_taken.pop(self.ends[source_index],None)
            return
        if h=='while':
            val,j=self.expr(ts,1,line)
            if not val:
                if self.loop and self.loop[-1]['start']==source_index:self.loop.pop()
                self.ip=self.ends[source_index]+1
            elif not self.loop or self.loop[-1]['start']!=source_index:
                self.loop.append({'kind':'while','start':source_index,'end':self.ends[source_index]})
            return
        if h=='endwhile':self.ip=self.ends[source_index];return
        if h=='for':
            name=ts[1].value
            start,j=self.expr(ts,2,line)
            end,j=self.expr(ts,j,line)
            self.v[name]=start
            self.loop.append({'kind':'for','start':source_index,'end':self.ends[source_index],
                              'var':name,'last':end})
            return
        if h=='next':
            l=self.loop[-1]
            cur=self.v[l['var']]
            if cur==l['last']:self.loop.pop()
            else:
                self.v[l['var']]=cur+(1 if cur<l['last'] else -1)
                self.ip=l['start']+1
            return
        if h=='break':
            l=self.loop.pop();self.ip=l['end']+1;return
        if h=='continue':
            l=self.loop[-1];self.ip=l['end'];return
        if h=='flushrecv':
            # receive_events describe future wait calls, not a socket backlog.
            self.flush_count+=1
            return
        if h=='sendln':
            values=[v for _,v in self.arguments(ts,1,line)]
            self.sent.append(b''.join(bytes([v]) if isinstance(v,int) else v for v in values))
            return
        if h=='waitregex':
            patterns=[v for _,v in self.arguments(ts,1,line)]
            if not self.receive_events:
                raise ValueError('waitregex called without an explicit receive event')
            event=self.receive_events.pop(0)
            self.v['result']=0
            self.v['inputstr']=b'' if event is None else event
            self.v['matchstr']=b''
            if event is not None:
                for index,pattern in enumerate(patterns,1):
                    matched=self.onig.search(pattern.decode('utf-8'),event.decode('utf-8'))
                    if matched is not None:
                        self.v['result']=index
                        self.v['matchstr']=matched['groups'][0].encode('utf-8')
                        break
            return
        # Output references must be initialized only after source values are read.
        output_first={'fileopen','filereadln','strcopy','tolower','sprintf2'}
        if h=='fileopen':
            ref,j=self.reference(ts,1,line)
            a=self.arguments(ts,j,line)
            path=a[0][1]
            if path in self.files:
                n=len(self.fd);self.fd[n]=[self.files[path],0];self.put(ref,n)
            else:self.put(ref,-1)
            return
        if h=='fileclose':return
        if h=='filereadln':
            fd,j=self.expr(ts,1,line);ref,j=self.reference(ts,j,line)
            data,offset=self.fd[fd]
            if offset>=len(data):out=b'';self.v['result']=1
            else:
                start=offset
                while offset<len(data) and data[offset] not in (10,13):offset+=1
                out=data[start:offset][:511]
                if offset<len(data):
                    c=data[offset];offset+=1
                    if c==13 and offset<len(data) and data[offset]==10:offset+=1
                self.v['result']=0
            self.fd[fd][1]=offset;self.put(ref,out);return
        if h=='str2int':
            ref,j=self.reference(ts,1,line)
            source,j=self.expr(ts,j,line)
            # This test model only needs decimals already validated by the
            # macro's input regex; it does not claim all native sscanf behavior.
            if not source or any(c not in b'0123456789' for c in source):
                raise ValueError('model str2int supports validated decimal digits only')
            self.put(ref,int(source,10))
            self.v['result']=1
            return
        if h in ('tolower','sprintf2'):
            ref,j=self.reference(ts,1,line)
            aa=[v for _,v in self.arguments(ts,j,line)]
            if h=='tolower':self.put(ref,aa[0].lower())
            else:self.put(ref,aa[0] % tuple(aa[1:]))
            return
        if h=='strcopy':
            src,j=self.expr(ts,1,line);start,j=self.expr(ts,j,line);count,j=self.expr(ts,j,line)
            ref,j=self.reference(ts,j,line)
            self.put(ref,src[max(1,start)-1:max(1,start)-1+count]);return
        if h in ('strtrim','strremove','strconcat','strreplace'):
            ref,j=self.reference(ts,1,line)
            name,index=ref;old=self.v[name] if index is None else self.v[name][index]
            aa=[v for _,v in self.arguments(ts,j,line)]
            if h=='strtrim':new=old.strip(aa[0])
            elif h=='strremove':new=old[:aa[0]-1]+old[aa[0]-1+aa[1]:]
            elif h=='strconcat':new=old+aa[0]
            else:
                start,pat,replacement=aa
                m=self.onig.search(pat.decode(),old[start-1:].decode())
                self.v['result']=0 if m is None else start+m['start']
                if m is None:new=old
                else:
                    a=start-1+m['start'];b=start-1+m['end']
                    new=old[:a]+replacement+old[b:]
            self.put(ref,new);return
        aa=[v for _,v in self.arguments(ts,1,line)]
        if h=='strlen':self.v['result']=len(aa[0])
        elif h=='strcompare':self.v['result']=(aa[0]>aa[1])-(aa[0]<aa[1])
        elif h=='strscan':self.v['result']=aa[0].find(aa[1])+1 if aa[0] and aa[1] else 0
        elif h=='strmatch':
            try:m=self.onig.search(aa[1].decode(),aa[0].decode())
            except (UnicodeDecodeError,ValueError):m=None
            self.v['result']=0 if m is None else m['start']+1
            if m is not None:self.v['matchstr']=m['groups'][0].encode()
        else:raise ValueError(f'Unsupported model command {h} at line {source_index+1}')


def main():
    p=argparse.ArgumentParser();p.add_argument('macro',type=Path);a=p.parse_args()
    passed=[];failed=[]
    def check(name,fn):
        try:fn();passed.append(name)
        except Exception as e:failed.append({'case':name,'error':repr(e)})
    def parse_case(data,kind,expected,ok=True):
        m=Model(a.macro);m.files[b'fixture.txt']=data
        m.v.update(input_path=b'fixture.txt',input_kind=kind)
        m.run('read_input')
        assert bool(m.v['parse_ok'])==ok,(m.v['parse_ok'],m.v.get('fatal_note'))
        if ok:
            count=m.v['host_count' if kind==0 else 'command_count']
            vals=m.v['hosts' if kind==0 else 'commands'][:count]
            assert vals==expected,vals
    cases=[
        ('single_host_no_final_newline',b'router01',0,[b'router01'],True),
        ('two_hosts_lf',b'router01\nswitch02\n',0,[b'router01',b'switch02'],True),
        ('two_hosts_crlf',b'router01\r\nswitch02\r\n',0,[b'router01',b'switch02'],True),
        ('utf8_bom_hosts',b'\xef\xbb\xbfrouter01\r\nswitch02',0,[b'router01',b'switch02'],True),
        ('blank_comments_trim',b'\n# hosts\n ; comment\n\t router01 \t\n',0,[b'router01'],True),
        ('empty_input',b'',0,[],True),
        ('duplicate_case',b'ROUTER01\nrouter01',0,[],False),
        ('host_injection',b'router01 /ssh',0,[],False),
        ('host_oversized_line',b'r'*600,0,[],False),
        ('commands_no_final_newline',b'show clock\nshow version',1,[b'show clock',b'show version'],True),
        ('commands_utf8_bom',b'\xef\xbb\xbfshow clock\r\n',1,[b'show clock'],True),
        ('command_pipe_include',b'show ip route | include 192.0.2.',1,[b'show ip route | include 192.0.2.'],True),
        ('reject_redirect_abbrev',b'show clock | red tftp://host/file',1,[],False),
        ('reject_append',b'show clock | append flash:file',1,[],False),
        ('reject_tee',b'show clock | tee flash:file',1,[],False),
        ('reject_help',b'show clock ?',1,[],False),
        ('reject_config',b'configure terminal',1,[],False),
        ('reject_ctrl',b'show clock\x03',1,[],False),
        ('command_240_bytes',b'show '+b'x'*235,1,[b'show '+b'x'*235],True),
        ('command_241_bytes',b'show '+b'x'*236,1,[],False),
        ('256_commands',b'\n'.join([b'show clock']*256),1,[b'show clock']*256,True),
        ('257_commands',b'\n'.join([b'show clock']*257),1,[],False),
    ]
    for name,data,kind,expect,ok in cases:
        check(name,lambda data=data,kind=kind,expect=expect,ok=ok:parse_case(data,kind,expect,ok))
    def quote_case(raw,expected):
        m=Model(a.macro);m.v.update(quote_source=raw)
        m.run('quote_argument')
        assert m.v['quote_result']==expected,(m.v['quote_result'],expected)
        assert m.v['quote_source']==b''
        assert m.v['quote_char']==b''
    for raw,expected in [(b'plain',b'plain'),(b'pa"ss',b'pa""ss'),
                         (b'; /passwd=evil',b'; /passwd=evil'),
                         (b'""',b'""""'),(b'p@ss\\x',b'p@ss\\x')]:
        check('quote_'+raw.decode(),lambda r=raw,e=expected:quote_case(r,e))
    def credential_case(raw,limit,ok):
        m=Model(a.macro);m.v.update(check_value=raw,check_limit=limit)
        m.run('check_credential')
        assert bool(m.v['credential_ok'])==ok
        assert m.v['check_value']==b''
    for raw,limit,ok in [(b'a'*128,128,True),(b'a'*129,128,False),
                         (b'a\tbc',128,False),(b'pass"; with spaces',128,True),
                         (b'',128,True),(b'a\x7f',128,False)]:
        check('credential_'+str(len(raw))+'_'+str(ok),lambda r=raw,l=limit,o=ok:credential_case(r,l,o))
    def budget_case(raw,allowed):
        m=Model(a.macro)
        m.v.update(inputstr=raw,tacacs_failure_limit=99)
        m.run('check_tacacs_limit')
        assert bool(m.v['budget_ok'])==allowed,('budget acceptance',raw,m.v['budget_ok'])
        if allowed:
            assert m.v['tacacs_failure_limit']==int(raw)
        else:
            assert m.v['tacacs_failure_limit']==99,'invalid budget mutated the limit'
    for raw in (b'1',b'2',b'3'):
        check('budget_accept_'+raw.decode(),lambda r=raw:budget_case(r,True))
    invalid_budgets=(b'',b'0',b'4',b'5',b'9',b'10',b'1000',b'-1',b'+2',
                     b'01',b'1.0',b' 2',b'2 ',b'2\n','２'.encode('utf-8'),b'a')
    for index,raw in enumerate(invalid_budgets):
        check('budget_reject_'+str(index),lambda r=raw:budget_case(r,False))
    def pair_case(users,passwords,allowed,disable_common=False):
        m=Model(a.macro)
        enables=[b'FAKE_SSH_ENABLE',b'FAKE_TELNET_ENABLE']
        m.v.update(ssh_user=list(users),ssh_pass=list(passwords),enable_pass=list(enables))
        m.run('check_ssh_pair')
        assert bool(m.v['credential_pair_ok'])==allowed
        expected_users=[users[0],b''] if disable_common else list(users)
        expected_passwords=[passwords[0],b''] if disable_common else list(passwords)
        expected_enables=[b'',enables[1]] if disable_common else enables
        assert m.v['ssh_user']==expected_users,'unexpected SSH username mutation'
        assert m.v['ssh_pass']==expected_passwords,'unexpected SSH password mutation'
        assert m.v['enable_pass']==expected_enables,'unexpected enable password mutation'
        assert m.v['tacacs_user_key']==b'' and m.v['common_user_key']==b''
    pairs=[
        ('different_users_different_passwords',(b'tac-user',b'local-user'),(b'tac-pass',b'local-pass'),True,False),
        ('different_users_same_password',(b'tac-user',b'local-user'),(b'same-pass',b'same-pass'),True,False),
        ('same_user_different_passwords_rejected',(b'ops',b'ops'),(b'tac-pass',b'local-pass'),False,False),
        ('case_folded_same_user_different_passwords_rejected',(b'OPS',b'ops'),(b'tac-pass',b'local-pass'),False,False),
        ('identical_pair_disabled',(b'ops',b'ops'),(b'same-pass',b'same-pass'),True,True),
        ('case_folded_identical_pair_disabled',(b'OPS',b'ops'),(b'same-pass',b'same-pass'),True,True),
        ('tacacs_only',(b'ops',b''),(b'tac-pass',b''),True,False),
        ('common_only',(b'',b'ops'),(b'',b'local-pass'),True,False),
        ('both_blank',(b'',b''),(b'',b''),True,False),
    ]
    for name,users,passwords,allowed,disable in pairs:
        check('ssh_pair_'+name,lambda u=users,p=passwords,o=allowed,d=disable:pair_case(u,p,o,d))
    report={'source_procedure_cases':len(passed)+len(failed),'passed':len(passed),'failures':failed,
            'limits':'Source-driven subset simulation, NOT native Tera Term execution or network tests.'}
    print(json.dumps(report,indent=2,ensure_ascii=False))
    raise SystemExit(bool(failed))


if __name__=='__main__':main()

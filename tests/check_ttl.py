"""Conservative structural/lexical checks for TTL; NOT the native interpreter.

The lexical rules and reserved words are grounded in upstream ttmparse.cpp
(TeraTermProject/teraterm), and manual/5/en/macro/syntax/*.html.
Checks quoting, identifiers, line/string limits, command names, expression
syntax, control-block structure, and label targets. It does not validate DDE,
GUI behavior, runtime variable types/initialization, or remote commands.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass
class Token:
    kind: str
    value: str
    start: int
    end: int


def tokenize(line: str) -> list[Token]:
    out = []
    i = 0
    while i < len(line):
        if line[i].isspace():
            i += 1
            continue
        if line[i] == ';':
            break
        a = i
        if line[i] in "\"'#":
            value = ''
            while i < len(line) and line[i] in "\"'#":
                c = line[i]
                i += 1
                if c == '#':
                    m = re.match(r'(?:\$[0-9a-fA-F]+|[0-9]+)', line[i:])
                    if not m:
                        raise ValueError('Invalid # character constant')
                    s = m.group()
                    n = int(s[1:],16) if s.startswith('$') else int(s)
                    if not 1 <= n <= 255:
                        raise ValueError('# character constant must be in 1..255')
                    value += chr(n)
                    i += len(s)
                else:
                    j = line.find(c, i)
                    if j < 0:
                        raise ValueError('Unclosed quoted string')
                    value += line[i:j]
                    i = j + 1
            out.append(Token('string',value,a,i))
            continue
        m = re.match(r'[a-zA-Z_][a-zA-Z_0-9]*',line[i:])
        if m:
            s=m.group()
            out.append(Token('name',s.lower(),i,i+len(s)))
            i += len(s)
            continue
        m = re.match(r'(?:\$[a-fA-F0-9]+|[0-9]+)',line[i:])
        if m:
            s=m.group()
            out.append(Token('number',s,i,i+len(s)))
            i += len(s)
            continue
        m = re.match(r'>>>|<<|>>|<=|>=|==|!=|<>|&&|\|\||[-+*/%&|^=<>~!()[\]:]',line[i:])
        if m:
            s=m.group()
            out.append(Token('symbol',s,i,i+len(s)))
            i += len(s)
            continue
        raise ValueError(f'Unexpected character {line[i]!r} at column {i+1}')
    return out


PRECEDENCE = {'||':1,'&&':2,'=':3,'==':3,'!=':3,'<>':3,'<':4,'>':4,'<=':4,'>=':4,
              'or':5,'|':5,'xor':6,'^':6,'and':7,'&':7,'<<':8,'>>':8,'>>>':8,
              '+':9,'-':9,'*':10,'/':10,'%':10}


def expression(ts: list[Token], i: int, minimum: int=0):
    if i >= len(ts):
        raise ValueError('Missing expression')
    t=ts[i]
    if t.value in ('+','-','~','!','not'):
        i=expression(ts,i+1,11)
    elif t.value == '(':
        i=expression(ts,i+1)
        if i>=len(ts) or ts[i].value!=')':
            raise ValueError('Missing closing parenthesis')
        i += 1
    elif t.kind in ('name','number'):
        i += 1
        if i<len(ts) and ts[i].value=='[':
            i=expression(ts,i+1)
            if i>=len(ts) or ts[i].value!=']':
                raise ValueError('Missing array closing bracket')
            i += 1
    else:
        raise ValueError('Integer expression cannot contain a string literal')
    while i<len(ts) and ts[i].value in PRECEDENCE and PRECEDENCE[ts[i].value]>=minimum:
        op=ts[i].value
        i=expression(ts,i+1,PRECEDENCE[op]+1)
    return i


def args(ts:list[Token],i:int):
    out=[]
    while i<len(ts):
        j=i+1 if ts[i].kind=='string' else expression(ts,i)
        out.append(ts[i:j])
        i=j
    return out


# Only stable, commonly used signatures are arity-checked. Unlisted commands
# still receive lexical, identifier, block and known-name checks.
ARITY={
    'call':(1,1),'goto':(1,1),'return':(0,0),'end':(0,0),'exit':(0,0),
    'break':(0,0),'continue':(0,0),'connect':(1,1),'disconnect':(0,1),
    'closett':(0,0),'testlink':(0,0),'flushrecv':(0,0),
    'send':(1,999),'sendln':(0,999),'wait':(1,10),'waitregex':(1,10),
    'waitln':(1,10),'recvln':(0,0),'waitn':(1,1),
    'setsync':(1,1),'setecho':(1,1),'setdebug':(1,1),'settitle':(1,1),
    'getdir':(1,1),'setdir':(1,1),'makepath':(3,3),
    'fileopen':(3,4),'fileclose':(1,1),'filecreate':(2,2),
    'filereadln':(2,2),'filewrite':(2,2),'filewriteln':(2,2),
    'filesearch':(1,1),'foldersearch':(1,1),'foldercreate':(1,1),
    'logopen':(3,8),'logclose':(0,0),'logpause':(0,0),'logstart':(0,0),
    'logwrite':(1,1),'logautoclosemode':(1,1),
    'strdim':(2,2),'intdim':(2,2),'strconcat':(2,2),'strcopy':(4,4),
    'strscan':(2,2),'strmatch':(2,2),'strtrim':(2,2),'strcompare':(2,2),
    'strreplace':(4,4),'strlen':(1,1),'str2int':(2,2),'int2str':(2,2),
    'tolower':(2,2),'toupper':(2,2),'sprintf2':(2,999),
    'uptime':(1,1),'mpause':(1,1),'pause':(1,1),
    'passwordbox':(2,3),'inputbox':(2,4),'messagebox':(2,3),
    'yesnobox':(2,3),'listbox':(3,6),'statusbox':(2,2),'closesbox':(0,0),
    'getenv':(2,2),'gettime':(1,3),'getdate':(1,3),'getttdir':(1,1),
    'random':(2,2),'setexitcode':(1,1),'regexoption':(1,999),
}


class Checker:
    def __init__(self, known:set[str]):
        self.known=known
        self.issues=[]
        self.stack=[]
        self.labels={}
        self.targets=[]
        self.constants={}
        self.commands={}
        self.line=0

    def issue(self,message):
        self.issues.append({'line':self.line,'message':message})

    def statement(self,ts):
        if not ts:
            return
        head=ts[0].value
        if head==':':
            if len(ts)!=2 or not re.fullmatch(r'[A-Za-z_0-9]+',ts[1].value):
                raise ValueError('Invalid label declaration')
            name=ts[1].value
            if name in self.labels:
                raise ValueError(f'Duplicate label {name}')
            self.labels[name]=self.line
            return
        # Assignment LHS is a variable, optionally indexed.
        j=1
        if j<len(ts) and ts[j].value=='[':
            j=expression(ts,j+1)
            if j>=len(ts) or ts[j].value!=']':
                raise ValueError('Missing array closing bracket')
            j+=1
        if j<len(ts) and ts[j].value=='=':
            if head in self.known:
                raise ValueError(f'Reserved command/operator used as variable: {head}')
            if j+1>=len(ts):
                raise ValueError('Assignment is missing a value')
            if ts[j+1].kind=='string':
                if j+2!=len(ts):
                    raise ValueError('Trailing tokens after string assignment')
                if j==1:
                    self.constants[head]=ts[j+1].value
            elif expression(ts,j+1)!=len(ts):
                raise ValueError('Trailing tokens after assignment expression')
            return
        if head not in self.known:
            raise ValueError(f'Unknown TTL command: {head}')
        self.commands[head]=self.commands.get(head,0)+1
        if head in ('if','elseif'):
            i=expression(ts,1)
            if i==len(ts):
                raise ValueError(f'{head} needs then or an inline statement')
            if ts[i].value=='then':
                if i+1!=len(ts):
                    raise ValueError('Trailing tokens after then')
                if head=='if':
                    self.stack.append(('if',self.line))
                elif not self.stack or self.stack[-1][0]!='if':
                    raise ValueError('elseif without matching if')
            elif head=='if':
                self.statement(ts[i:])
            else:
                raise ValueError('elseif requires then')
            return
        if head=='else':
            if len(ts)!=1 or not self.stack or self.stack[-1][0]!='if':
                raise ValueError('Invalid else')
            return
        if head in ('while','until','for','do'):
            if head in ('while','until') and expression(ts,1)!=len(ts):
                raise ValueError(f'Trailing tokens in {head} condition')
            if head=='for' and len(args(ts,1))!=3:
                raise ValueError('for requires a variable, start and end')
            self.stack.append((head,self.line))
            return
        if head in ('endif','endwhile','enduntil','next','loop'):
            expected={'endif':'if','endwhile':'while','enduntil':'until','next':'for','loop':'do'}[head]
            if not self.stack or self.stack[-1][0]!=expected:
                raise ValueError(f'{head} has no matching {expected}')
            self.stack.pop()
            if head!='loop' and len(ts)!=1:
                raise ValueError(f'Trailing tokens after {head}')
            return
        aa=args(ts,1)
        if head in ARITY:
            lo,hi=ARITY[head]
            if not lo<=len(aa)<=hi:
                raise ValueError(f'{head} expects {lo}..{hi} parameters; parsed {len(aa)}')
        if head in ('call','goto'):
            if len(aa)!=1 or len(aa[0])!=1 or aa[0][0].kind not in ('name','number'):
                raise ValueError(f'{head} requires a label identifier')
            self.targets.append((self.line,aa[0][0].value))

    def check(self,path:Path):
        raw=path.read_bytes()
        text=raw.decode('utf-8-sig')
        in_comment=False
        max_line=0
        for n,line in enumerate(text.splitlines(),1):
            self.line=n
            max_line=max(max_line,len(line.encode('utf-8')))
            if len(line.encode('utf-8'))>1023:
                self.issue('Source line exceeds 1023 bytes; native parser may truncate')
            # Handle /* */ outside strings without treating markers in literals as comments.
            cleaned=''
            i=0
            quote=None
            while i<len(line):
                if in_comment:
                    e=line.find('*/',i)
                    if e<0:
                        break
                    i=e+2
                    in_comment=False
                    continue
                if quote:
                    cleaned+=line[i]
                    if line[i]==quote:
                        quote=None
                    i+=1
                    continue
                if line[i]==';':
                    break
                if line.startswith('/*',i):
                    in_comment=True
                    i+=2
                    continue
                if line[i] in "\"'":
                    quote=line[i]
                cleaned+=line[i]
                i+=1
            try:
                ts=tokenize(cleaned)
                for t in ts:
                    if t.kind=='name' and len(t.value)>31:
                        self.issue(f'Identifier exceeds 31 characters: {t.value}')
                    if t.kind=='string' and len(t.value.encode('utf-8'))>511:
                        self.issue('String constant exceeds 511 bytes')
                self.statement(ts)
            except ValueError as e:
                self.issue(str(e))
        if in_comment:
            self.issue('Unclosed /* block comment')
        for kind,n in self.stack:
            self.line=n
            self.issue(f'Unclosed {kind} block')
        for n,target in self.targets:
            if target not in self.labels:
                self.line=n
                self.issue(f'Undefined label: {target}')
        return {'file':str(path),'lines':len(text.splitlines()),'max_line_bytes':max_line,
                'labels':len(self.labels),'command_types':len(self.commands),
                'issues':self.issues,'limitations':'Not a native TTL execution or full type checker.'}


# Reserved keywords are language facts from the official TTL command catalog
# and TeraTermProject/teraterm/teraterm/ttpmacro/ttmparse.cpp (main, 2026-10-21).
# This self-contained list avoids shipping upstream implementation source.
_RESERVED_WORDS = """
and basename beep bplusrecv bplussend break bringupbox call
callmenu changedir checksum16 checksum16file checksum32 checksum32file checksum8 checksum8file
clearscreen clipb2var closesbox closett code2str connect continue crc16
crc16file crc32 crc32file cygconnect delpassword delpassword2 dirname dirnamebox
disconnect dispstr do else elseif enablekeyb end endif
enduntil endwhile exec execcmnd exit expandenv fileclose fileconcat
filecopy filecreate filedelete filelock filemarkptr filenamebox fileopen fileread
filereadln filerename filesearch fileseek fileseekback filestat filestrseek filestrseek2
filetruncate fileunlock filewrite filewriteln findclose findfirst findnext flushrecv
foldercreate folderdelete foldersearch for getdate getdir getenv getfileattr
gethostname getipv4addr getipv6addr getmodemstatus getpassword getpassword2 getspecialfolder gettime
gettitle getttdir getttpos getver goto if ifdefined include
inputbox int2str intdim ispassword ispassword2 kmtfinish kmtget kmtrecv
kmtsend listbox loadkeymap logautoclosemode logclose loginfo logopen logpause
logrotate logstart logwrite loop makepath messagebox mpause next
not or outputdebugstring passwordbox pause quickvanrecv quickvansend random
recvfile recvln regexoption restoresetup return rotateleft rotateright scprecv
scpsend send sendbinary sendbreak sendbroadcast sendfile sendkcode sendln
sendlnbroadcast sendlnmulticast sendmulticast sendtext setbaud setdate setdebug setdir
setdlgpos setdtr setecho setenv setexitcode setfileattr setflowctrl setmulticastname
setpassword setpassword2 setrts setserialdelaychar setserialdelayline setspeed setsync settime
settitle show showtt sprintf sprintf2 statusbox str2code str2int
strcompare strconcat strcopy strdim strinsert strjoin strlen strmatch
strremove strreplace strscan strspecial strsplit strtrim testlink then
tolower toupper unlink until uptime var2clipb wait wait4all
waitevent waitln waitn waitrecv waitregex while xmodemrecv xmodemsend
xor yesnobox ymodemrecv ymodemsend zmodemrecv zmodemsend
"""


def known_words():
    return set(_RESERVED_WORDS.split())


def main():
    p=argparse.ArgumentParser()
    p.add_argument('file',type=Path)
    a=p.parse_args()
    report=Checker(known_words()).check(a.file)
    print(json.dumps(report,indent=2,ensure_ascii=False))
    raise SystemExit(bool(report['issues']))


if __name__=='__main__':
    main()
"""Source-driven tests for preview, preflight, reports and interruption paths.

Extends the existing limited TTL Model with in-memory files and scripted UI.
Authentication and command transactions are fixtures, NOT a terminal emulator.
Network access in preview is an immediate test failure.
"""
import argparse
import json
from pathlib import Path
from test_collector_procedures import Model


class Workflow(Model):
    def __init__(self, macro, mode=1, preview=True, grouping=0):
        super().__init__(macro)
        self.mode, self.preview, self.grouping = mode, preview, grouping
        self.root = b'C:\\Logs'
        self.server = b'192.0.2.20'
        self.files.update({b'hosts': b'SW01\nSW02',
                           b'commands': b'show clock\nshow interfaces Gi0/1',
                           b'C:\\Collector\\collector.ini': b'[Tera Term]'})
        self.fd_paths, self.dirs, self.stack = {}, set(), []
        self.credential_dialogs = self.auth_attempts = 0
        self.command_calls, self.progress = [], []
        self.outcomes, self.auth_fail = {}, set()
        self.tacacs_limit = b'3'
        self.messages = []
        self.tick = 0
        self.exit_code = None
        self.existing_log = False

    def execute(self):
        self.ip = 0
        while 0 <= self.ip < len(self.lines):
            self.steps += 1
            assert self.steps < 500000, 'step limit'
            i = self.ip
            self.ip += 1
            self.step(self.tokens[i], self.lines[i], i)

    def step(self, ts, line, source_index):
        if not ts:
            return
        h = ts[0].value
        if len(ts) > 1 and ts[1].value == '=':
            return super().step(ts, line, source_index)
        if h == 'call':
            label = ts[1].value
            if label == 'try_ssh':
                assert not self.preview, 'authentication attempted in preview'
                self.auth_attempts += 1
                ok = self.v['host'] not in self.auth_fail
                self.v.update(login_ok=int(ok), auth_status=b'EXEC_PROMPT_REACHED' if ok else b'SSH_NOT_CONNECTED',
                              learned_prompt=self.v['host']+b'#')
                return
            if label == 'run_command':
                assert not self.preview, 'command attempted in preview'
                if self.v['phase'] == b'COMMAND':
                    key = (self.v['host'], self.v['current_command_no'])
                    self.command_calls.append((key, self.v['wire_command']))
                    status, ok, prompt = self.outcomes.get(key, (b'LOCAL_CLI_DONE', 1, 1))
                else:
                    status, ok, prompt = b'LOCAL_CLI_DONE', 1, 1
                self.v.update(transaction_status=status, transaction_ok=ok, prompt_returned=prompt)
                return
            self.stack.append(self.ip)
            self.ip = self.labels[label] + 1
            return
        if h == 'return':
            self.ip = self.stack.pop() if self.stack else -1
            return
        if h == 'goto':
            self.ip = self.labels[ts[1].value] + 1
            return
        if h == 'end':
            self.ip = -1
            return
        if h in ('strdim', 'intdim'):
            n, _ = self.expr(ts, 2, line)
            self.v[ts[1].value] = [b'' if h == 'strdim' else 0] * n
            return
        if h == 'getdir':
            self.v[ts[1].value] = b'C:\\Collector'
            return
        if h in ('gettime', 'random', 'int2str'):
            ref, j = self.reference(ts, 1, line)
            aa = [v for _, v in self.arguments(ts, j, line)]
            if h == 'int2str':
                value = str(aa[0]).encode()
            elif h == 'random':
                value = 123456
            else:
                self.tick += 1
                value = {b'%Y%m%d_%H%M%S': b'20261021_090001',
                         b'%Y-%m-%d %H:%M:%S': b'2026-10-21 09:00:01',
                         b'%H%M%S': f'{self.tick//3600:02d}{self.tick//60%60:02d}{self.tick%60:02d}'.encode()}[aa[0]]
            self.put(ref, value)
            return
        if h == 'fileopen':
            ref, j = self.reference(ts, 1, line)
            aa = [v for _, v in self.arguments(ts, j, line)]
            path, append = aa[:2]
            readonly = len(aa) > 2 and aa[2]
            if readonly and path not in self.files:
                self.put(ref, -1)
                return
            data = self.files.setdefault(path, b'')
            n = len(self.fd)
            self.fd[n] = [data, len(data) if append else 0]
            self.fd_paths[n] = path
            self.put(ref, n)
            return
        if h in ('filewrite', 'filewriteln'):
            aa = [v for _, v in self.arguments(ts, 1, line)]
            fd, data = aa
            if isinstance(data, int):
                data = bytes([data & 255])
            if h == 'filewriteln':
                data += b'\r\n'
            old, pos = self.fd[fd]
            old = old[:pos] + data + old[pos+len(data):]
            self.fd[fd] = [old, pos+len(data)]
            self.files[self.fd_paths[fd]] = old
            return
        if h == 'fileclose':
            return
        if h in ('logopen', 'logwrite', 'logclose'):
            assert not self.preview, 'terminal logging attempted in preview'
            if h == 'logopen':
                self.v['result'] = 0
            return
        if h in ('connect', 'sendln'):
            raise AssertionError('unexpected real terminal operation: '+h)
        if h == 'testlink':
            self.v['result'] = 0
            return
        if h == 'filesearch':
            aa = [v for _, v in self.arguments(ts, 1, line)]
            self.v['result'] = int(aa[0] in self.files or (self.existing_log and b'_c001.txt' in aa[0]))
            return
        if h == 'foldercreate':
            aa = [v for _, v in self.arguments(ts, 1, line)]
            self.v['result'] = int(aa[0].lower() in self.dirs)
            self.dirs.add(aa[0].lower())
            return
        if h in ('filenamebox', 'dirnamebox', 'inputbox', 'passwordbox', 'listbox', 'yesnobox',
                 'messagebox', 'statusbox', 'closesbox', 'setexitcode'):
            aa = [v for _, v in self.arguments(ts, 1, line)]
            message = aa[0] if aa else b''
            if h == 'filenamebox':
                self.v.update(result=1, inputstr=b'hosts' if message.startswith('ホスト'.encode()) else b'commands')
            elif h == 'dirnamebox':
                self.v.update(result=1, inputstr=self.root)
            elif h == 'listbox':
                if message.startswith('保存方式'.encode()):
                    self.v['result'] = self.mode
                elif message.startswith('統合'.encode()):
                    self.v['result'] = self.grouping
                else:
                    self.v['result'] = int(self.preview)
            elif h == 'inputbox':
                if message.startswith(b'TFTP'):
                    value = self.server
                elif message.startswith('1コマンド'.encode()):
                    value = b'120'
                elif message.startswith('TACACS用SSHでEXEC'.encode()):
                    value = self.tacacs_limit
                else:
                    assert not self.preview, 'username requested in preview'
                    self.credential_dialogs += 1
                    value = b'FAKE_USERNAME' if message.startswith('TACACS用SSHのユーザー'.encode()) else b''
                self.v['inputstr'] = value
            elif h == 'passwordbox':
                assert not self.preview, 'password requested in preview'
                self.credential_dialogs += 1
                self.v['inputstr'] = b'FAKE_PASSWORD' if message.startswith('TACACS用SSHのパスワード'.encode()) else b''
            elif h == 'yesnobox':
                self.v['result'] = 1
            elif h == 'setexitcode':
                self.exit_code = aa[0]
            elif h == 'messagebox':
                self.messages.append(message)
            elif h == 'statusbox':
                self.progress.append(message)
            return
        return super().step(ts, line, source_index)

    def content(self, basename):
        matches = [data for name, data in self.files.items() if name.endswith(b'\\'+basename.encode())]
        assert len(matches) == 1, basename
        return matches[0]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('macro',type=Path)
    macro=p.parse_args().macro
    passed=[]
    for mode, group in ((0,0),(0,1),(1,0),(2,0)):
        m=Workflow(macro,mode=mode,grouping=group)
        m.execute()
        assert m.exit_code==4, m.messages
        assert m.auth_attempts==m.credential_dialogs==0
        assert not m.command_calls
        assert len(m.content('collection_plan.tsv').splitlines())==5
        assert b'YYYYMMDD_HHMMSS' in m.content('collection_plan.tsv') if mode else True
        assert b'PRECHECK_ONLY_NO_CONNECTION' in m.content('summary.tsv')
        if mode==2:
            assert m.content('tftp_folders.txt').splitlines()==[b'SW01',b'SW02']
        passed.append(f'preview_mode{mode}_group{group}_no_auth_no_connection')

    m=Workflow(macro);m.root=b'C:\\'+b'a'*125
    m.files[b'hosts']=b'h'*40
    m.execute()
    assert m.exit_code==2 and not m.credential_dialogs and not m.auth_attempts
    assert b'LOCAL_PATH_TOO_LONG' in m.content('collection_plan.tsv')
    passed.append('overlong_local_path_stops_before_credentials')

    m=Workflow(macro,mode=2);m.server=b's'*200
    m.files[b'commands']=b'show '+b'x'*230
    m.execute()
    assert m.exit_code==2 and not m.auth_attempts
    assert b'TFTP_COMMAND_TOO_LONG' in m.content('collection_plan.tsv')
    passed.append('overlong_tftp_command_stops_before_credentials')

    m=Workflow(macro);m.files[b'hosts']=b'NUL\nh0001_NUL'
    m.execute()
    assert m.exit_code==2 and not m.auth_attempts
    passed.append('normalized_host_collision_before_auth')

    m=Workflow(macro,preview=False);m.execute()
    assert m.exit_code==0 and len(m.command_calls)==4
    assert m.content('hosts_need_review.txt')==b''
    rows=[r.split(b'\t') for r in m.content('summary.tsv').splitlines()]
    assert all(len(r)==11 for r in rows)
    commands=[r for r in rows if r[3]==b'COMMAND']
    assert len(commands)==4
    assert commands[1][7]==b'show interfaces Gi0/1'
    assert all(r[8] and int(r[9])>=0 and r[10] for r in commands)
    assert all(b'FAKE_PASSWORD' not in data and b'FAKE_USERNAME' not in data for data in m.files.values())
    passed.append('local_success_full_command_elapsed_and_no_credentials_in_reports')

    m=Workflow(macro,preview=False)
    m.outcomes[(b'SW01',1)]=(b'CLI_ERROR_TEXT_REVIEW',0,1)
    m.execute()
    assert m.exit_code==1 and m.content('hosts_need_review.txt').splitlines()==[b'SW01']
    passed.append('partial_command_failure_review_host_only')

    m=Workflow(macro,preview=False)
    m.outcomes[(b'SW01',1)]=(b'COMMAND_TIMEOUT',0,0)
    m.execute()
    assert len(m.command_calls)==3 and m.exit_code==1
    rows=[r.split(b'\t') for r in m.content('summary.tsv').splitlines()]
    skipped=[r for r in rows if r[5]==b'SKIPPED_SESSION_UNSAFE']
    assert len(skipped)==1 and skipped[0][7]==b'show interfaces Gi0/1'
    assert skipped[0][8:]==[b'',b'',b'']
    passed.append('timeout_skipped_command_has_no_stale_time_or_log')

    m=Workflow(macro,preview=False);m.auth_fail={b'SW01'};m.tacacs_limit=b'1'
    m.execute()
    assert m.exit_code==1 and m.auth_attempts==1 and not m.command_calls
    assert m.content('hosts_need_review.txt').splitlines()==[b'SW01',b'SW02']
    passed.append('lockout_cap_lists_failed_and_unattempted_without_retry')

    m=Workflow(macro,preview=False);m.existing_log=True;m.execute()
    assert len(m.command_calls)==2 and m.exit_code==1
    assert m.content('hosts_need_review.txt').splitlines()==[b'SW01',b'SW02']
    passed.append('existing_split_logs_skip_command_without_overwrite')

    m=Workflow(macro,preview=False,mode=2);m.execute()
    assert m.exit_code==3
    assert m.content('hosts_need_review.txt')==b''
    assert m.content('hosts_tftp_unverified.txt').splitlines()==[b'SW01',b'SW02']
    passed.append('tftp_unverified_separate_from_failed_hosts')

    m=Workflow(macro)
    pattern=m.v['cli_error_re'].decode()
    for text in ('% Appending is not supported in this file system',
                 '% This command is not supported', '% Not enough space',
                 'No space left on device', 'No such file or directory', 'Timed out'):
        assert m.onig.search(pattern,text) is not None, text
    for text in ('No errors detected', 'Current input rate 1000 bits/sec',
                 '  Feature not supported: no', 'show logging | include not supported'):
        assert m.onig.search(pattern,text) is None, text
    passed.append('unsupported_storage_and_timeout_error_patterns')
    print(json.dumps({'passed':len(passed),'scenarios':passed,
                      'limitations':'In-memory TTL workflow model; authentication, transport, GUI and logging are fixtures, not native tests.'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

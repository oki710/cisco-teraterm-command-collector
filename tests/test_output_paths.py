"""Check the actual TTL naming procedures with the existing limited Model.

Tests collision avoidance, host isolation and TFTP relative paths. No native
Tera Term, Windows filesystem, network transfer or device is exercised.
"""
import argparse
import json
from pathlib import Path, PureWindowsPath
from test_collector_procedures import Model


def setup(macro, host=b'SW01', host_no=1, mode=1, random=123456):
    m = Model(macro)
    m.v.update(host=host, host_no=host_no, output_mode=mode, group_all=0,
               run_dir=b'C:\\CiscoLogs\\cisco_20261021_090000_123456',
               command_stamp=b'20261021_090001', command_index=0,
               current_command_no=1, run_random=random,
               tftp_server=b'192.0.2.20')
    m.files[b'commands'] = b'show clock\nshow interfaces Gi0/1\nshow interfaces Gi0:1\nshow clock'
    m.v.update(input_path=b'commands', input_kind=1)
    m.run('read_input')
    assert m.v['parse_ok']
    m.run('make_host_name')
    return m


def name(m, index=0):
    m.v.update(command_index=index, current_command_no=index+1)
    m.run('make_command_paths')
    return m.v['local_path'].decode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('macro', type=Path)
    macro = parser.parse_args().macro
    passed = []

    paths = []
    for n, host in enumerate((b'SW01', b'SW02'), 1):
        m = setup(macro, host, n)
        for index in (0, 1):
            path = name(m, index)
            assert PureWindowsPath(path).parent.name == host.decode()
            assert PureWindowsPath(path).name.startswith(host.decode() + '_show_')
            assert '_20261021_090001_' in path
            assert len(path.encode()) <= 240
            paths.append(path)
    assert len(set(paths)) == 4
    passed.append('two_hosts_two_commands_in_separate_folders')

    m = setup(macro)
    assert m.v['slugs'][1] == m.v['slugs'][2]
    assert name(m, 1) != name(m, 2)
    assert name(m, 0) != name(m, 3)
    assert '/' not in PureWindowsPath(name(m, 1)).name
    assert ':' not in PureWindowsPath(name(m, 1)).name
    passed.append('same_second_duplicate_and_sanitized_command_collisions')

    before = name(m)
    m.v['command_stamp'] = b'20261022_000001'
    after = name(m)
    assert before != after and '_20261022_000001_' in after
    passed.append('per_command_timestamp_and_date_rollover')

    for original, expected in ((b'CON', b'h0001_CON'),
                               (b'nul.example.net', b'h0001_nul.example.net'),
                               (b'COM1', b'h0001_COM1'),
                               (b'sw01.', b'sw01_h0001'),
                               (b'192.0.2.10', b'192.0.2.10')):
        m = setup(macro, original)
        assert m.v['host_folder'] == expected
        assert PureWindowsPath(name(m)).parent.name == expected.decode()
    passed.append('windows_reserved_names_trailing_dot_and_ip')

    names = [setup(macro, b'a'*40 + ending, n).v['host_folder']
             for n, ending in enumerate((b'one', b'two'), 1)]
    assert names == [b'a'*40 + b'_h0001', b'a'*40 + b'_h0002']
    passed.append('long_hosts_with_same_prefix_are_distinct')

    urls = []
    for random in (123456, 654321):
        m = setup(macro, mode=2, random=random)
        path = name(m)
        url = m.v['tftp_url'].decode()
        assert url.startswith('tftp://192.0.2.20/SW01/SW01_show_clock_20261021_090001_c001_r')
        assert '\\' not in url
        assert PureWindowsPath(path).parent.name == 'SW01'
        assert path.endswith('_c001_tftp.txt')
        assert 'c002_tftp.txt' in name(m, 1)
        urls.append(url)
    assert urls[0] != urls[1]
    passed.append('tftp_host_subdirectory_command_receipt_and_run_collision')

    m = setup(macro, mode=0)
    assert name(m).endswith('\\h0001_SW01__all.txt')
    assert name(m, 0) == name(m, 1)
    m.v['group_all'] = 1
    assert name(m).endswith('\\all_hosts.txt')
    passed.append('existing_aggregate_modes_preserved')

    text = macro.read_text(encoding='utf-8-sig')
    assert "listbox '保存方式を選択してください。' title output_choices 1" in text
    assert text.index("gettime command_stamp") < text.index('call make_command_paths')
    assert text.index('filesearch local_path') < text.index('logopen local_path')
    assert 'logopen local_path 0 log_append 1 0 1 0' in text
    passed.append('split_default_and_file_open_guard_wiring_static_check')

    print(json.dumps({'passed': len(passed), 'cases': passed,
                      'sample_paths': paths, 'sample_tftp_url': urls[0],
                      'limits': 'TTL subset model plus static wiring checks; no native logging or TFTP test.'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Disk monitor contracts: thresholds, state, bounded read-only suggestions."""
from __future__ import annotations

import importlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


def module():
    return importlib.import_module('paulshaclaw.core.space_pressure_alert')


class Sender:
    def __init__(self):
        self.sent = []

    def send_message(self, *, chat_id, text):
        self.sent.append((chat_id, text))


class Bindings:
    def lookup_chat_id(self, user_id):
        return {7: 70, 8: 70}.get(user_id)


def monitor(tmp_path, *, values=(99,), config=None, sender=None, clock=None, scan=None):
    m = module()
    feed = iter(values)
    return m.SpacePressureAlerter(
        sender=sender or Sender(), bindings=Bindings(), allowed_user_ids=[7, 8, 9],
        state_path=tmp_path / 'space-monitor.json',
        config=config or m.SpaceConfig(interval_seconds=1),
        read_root=lambda: m.parse_df(f'Avail Used 1G-blocks\n{next(feed)}G 800G 1000G\n'),
        scan=scan or (lambda: {'top_dirs': [], 'suggestions': [], 'scan_errors': []}),
        clock=clock or itertools.count().__next__,
    )


@pytest.mark.parametrize(('avail', 'expected'), [(101, 'ok'), (100, 'ok'), (99, 'warn'), (50, 'warn'), (49, 'critical'), (120, 'ok')])
def test_df_boundaries_and_state_schema(tmp_path, avail, expected):
    a = monitor(tmp_path, values=[avail])
    a.check_and_alert()
    state = json.loads(a.state_path.read_text())
    assert state['root'] == {'mount': '/', 'avail_gb': avail, 'used_gb': 800, 'size_gb': 1000, 'use_pct': 80}
    assert state['level'] == expected
    assert state['thresholds'] == {'warn_gb': 100, 'critical_gb': 50, 'recover_gb': 120}
    assert type(state['alerting']) is bool
    assert state['auto_reclaim'] is False
    assert state['vhdx']['path'] is None and state['vhdx']['size_gb'] is None
    assert '未知' in state['vhdx']['note']
    assert isinstance(state['top_dirs'], list) and isinstance(state['suggestions'], list)
    assert isinstance(state['checked_at'], str)


def test_hysteresis_escalates_once_per_level_until_recovery(tmp_path):
    sender = Sender()
    a = monitor(tmp_path, values=[101, 99, 100, 119, 99, 49, 50, 49, 120, 99], sender=sender)
    for _ in range(10):
        a.check_and_alert()
    assert len(sender.sent) == 4  # warn, critical, recovery, new warn; same chat deduplicated
    assert [text.split()[0] for _, text in sender.sent] == ['⚠️', '🚨', '✅', '⚠️']
    assert {chat for chat, _ in sender.sent} == {70}


def test_interval_and_disabled_do_not_repeat_measurement(tmp_path):
    now = [0.0]
    a = monitor(tmp_path, values=[99, 49], clock=lambda: now[0])
    a.check_and_alert()
    a.check_and_alert()
    assert json.loads(a.state_path.read_text())['level'] == 'warn'
    now[0] = 1.0
    a.check_and_alert()
    assert json.loads(a.state_path.read_text())['level'] == 'critical'
    a.config = module().SpaceConfig(disabled=True)
    now[0] = 5000
    a.check_and_alert()  # exhausted feed must never be read


def test_config_invalid_defaults_clamps_and_never_auto_reclaims():
    m = module()
    c = m.config_from_env({'PSC_SPACE_WARN_GB': '80', 'PSC_SPACE_CRITICAL_GB': '90', 'PSC_SPACE_RECOVER_GB': '70', 'PSC_SPACE_INTERVAL_SECONDS': 'bad', 'PSC_SPACE_AUTO_RECLAIM': '1'})
    assert (c.warn_gb, c.critical_gb, c.recover_gb) == (80, 80, 80)
    assert c.interval_seconds == 1200
    c = m.config_from_env({'PSC_SPACE_WARN_GB': '-1', 'PSC_SPACE_SCAN_SECONDS': 'nan', 'PSC_SPACE_DISABLED': '1', 'PSC_SPACE_SCAN_ROOTS': '/a:/b/*', 'PSC_SPACE_EXCLUDES': '/a/keep:/b/keep'})
    assert c.warn_gb == 100 and c.scan_seconds > 0 and c.disabled
    assert c.scan_roots == ('/a', '/b/*') and c.excludes == ('/a/keep', '/b/keep')


@pytest.mark.parametrize('bad', ['', 'Avail Used Size\nbad 2G 3G', 'Avail Used Size\n1G 2G 0G', 'Avail Used Size\n-1G 2G 3G'])
def test_invalid_df_fails_without_fabricating_capacity(bad):
    with pytest.raises(ValueError):
        module().parse_df(bad)


def test_read_and_state_write_failures_still_leave_listener_usable(tmp_path):
    sender = Sender()
    a = monitor(tmp_path, sender=sender)
    a.state_path.mkdir()  # atomic rename cannot replace a directory
    a.check_and_alert()
    assert len(sender.sent) == 1
    a._read_root = lambda: (_ for _ in ()).throw(OSError('df unavailable'))
    a.check_and_alert()
    assert len(sender.sent) == 1


def test_scan_failure_keeps_capacity_alert_and_unknown_scan(tmp_path):
    a = monitor(tmp_path, scan=lambda: (_ for _ in ()).throw(TimeoutError('scan budget')))
    a.check_and_alert()
    state = json.loads(a.state_path.read_text())
    assert state['level'] == 'warn' and state['scan_errors']
    assert state['suggestions'] == []


def test_sender_failure_is_not_retried_until_recovery(tmp_path):
    class FailingSender(Sender):
        def send_message(self, *, chat_id, text):
            super().send_message(chat_id=chat_id, text=text)
            raise OSError('offline')
    sender = FailingSender()
    a = monitor(tmp_path, values=[49, 49], sender=sender)
    a.check_and_alert()
    a.check_and_alert()
    assert len(sender.sent) == 1
    assert json.loads(a.state_path.read_text())['alerting'] is True


def test_vhdx_only_reads_explicit_regular_file(tmp_path):
    vhdx = tmp_path / 'ext4.vhdx'
    vhdx.write_bytes(b'123')
    a = monitor(tmp_path, config=module().SpaceConfig(vhdx_path=str(vhdx)))
    a.check_and_alert()
    state = json.loads(a.state_path.read_text())
    assert state['vhdx']['size_gb'] == 3 / 1024**3
    assert state['vhdx']['path'] == str(vhdx)


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], check=True, text=True, capture_output=True).stdout.strip()


@pytest.fixture
def repositories(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.name', 'Space Test')
    git(repo, 'config', 'user.email', 'space@example.invalid')
    (repo / '.gitignore').write_text('target/\n')
    git(repo, 'add', '.gitignore')
    git(repo, 'commit', '-m', 'base')
    remote = tmp_path / 'remote.git'
    remote.mkdir()
    git(remote, 'init', '--bare')
    git(repo, 'remote', 'add', 'origin', str(remote))
    git(repo, 'push', '-u', 'origin', 'main')
    merged = tmp_path / 'merged'
    git(repo, 'worktree', 'add', '-b', 'feature/merged', str(merged))
    unmerged = tmp_path / 'unmerged'
    git(repo, 'worktree', 'add', '-b', 'feature/unmerged', str(unmerged))
    (unmerged / 'new.txt').write_text('new')
    git(unmerged, 'add', 'new.txt')
    git(unmerged, 'commit', '-m', 'unmerged')
    git(unmerged, 'push', '-u', 'origin', 'feature/unmerged')
    git(repo, 'push', 'origin', 'main:refs/heads/feature/test-ci-r1')
    proc = tmp_path / 'proc'
    proc.mkdir()
    return repo, merged, unmerged, proc


def age_tree(path):
    for item in [*path.rglob('*'), path]:
        os.utime(item, (1, 1))


def scan_config(*roots, **kwargs):
    return module().SpaceConfig(scan_roots=tuple(map(str, roots)), scan_seconds=10, **kwargs)


def test_four_suggestion_classes_are_ordered_and_never_delete(repositories, tmp_path):
    repo, merged, unmerged, proc = repositories
    target = unmerged / 'target'
    target.mkdir()
    (target / 'output').write_text('keep')
    tmp = tmp_path / 'job-tmp'
    tmp.mkdir()
    (tmp / 'output').write_text('keep')
    age_tree(target)
    age_tree(tmp)
    before = git(repo, 'show-ref')
    result = module().scan_paths(scan_config(repo, merged, unmerged, tmp), proc=proc)
    assert result['scan_errors'] == []
    assert [item['action'] for item in result['suggestions']] == ['remove_worktree', 'remove_target', 'remove_tmp', 'remove_remote_branch']
    assert result['suggestions'][0]['path'] == str(merged)
    assert result['suggestions'][0]['branch'] == 'feature/merged'
    assert result['suggestions'][3]['branch'] == 'feature/test-ci-r1'
    assert not any(item.get('path') == str(repo) for item in result['suggestions'])
    assert not any(item.get('path') == str(unmerged) for item in result['suggestions'])
    assert (target / 'output').read_text() == (tmp / 'output').read_text() == 'keep'
    assert git(repo, 'show-ref') == before and (merged / '.git').exists()
    assert git(repo, 'ls-remote', '--heads', 'origin', 'feature/test-ci-r1')


def test_busy_live_cwd_and_cmdline_exclude_target_and_worktree(repositories):
    repo, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    age_tree(target)
    # A real long-lived process, isolated /proc view with its actual PID entries.
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], cwd=target)
    try:
        (proc / str(child.pid)).symlink_to(Path('/proc') / str(child.pid), target_is_directory=True)
        result = module().scan_paths(scan_config(merged), proc=proc)
        assert next(item for item in result['top_dirs'] if item['path'] == str(target))['busy'] is True
        assert result['suggestions'] == []
    finally:
        child.terminate()
        child.wait(timeout=5)


@pytest.mark.parametrize('command', ['cargo', 'rustc', 'test-binary'])
def test_cmdline_paths_mark_busy_even_with_unrelated_cwd(repositories, command):
    _, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    age_tree(target)
    pid = proc / '100'
    pid.mkdir()
    (pid / 'cwd').symlink_to(proc)
    (pid / 'cmdline').write_bytes(f'{command}\0--output={target}/debug/output\0'.encode())
    result = module().scan_paths(scan_config(merged), proc=proc)
    assert result['top_dirs'][0]['busy'] is True
    assert result['top_dirs'][0]['reclaimable'] is False
    assert result['suggestions'] == []


def test_recent_nested_artifact_dirty_worktree_and_excludes_prevent_suggestions(repositories, tmp_path):
    _, merged, unmerged, proc = repositories
    target = unmerged / 'target'
    target.mkdir()
    age_tree(target)
    nested = target / 'nested'
    nested.mkdir()
    (nested / 'new').write_text('fresh')
    os.utime(target, (1, 1))
    (merged / 'untracked').write_text('dirty')
    stale = tmp_path / 'old-tmp'
    stale.mkdir()
    age_tree(stale)
    result = module().scan_paths(scan_config(merged, unmerged, stale, excludes=(str(stale),)), proc=proc)
    assert not any(item['action'] != 'remove_remote_branch' for item in result['suggestions'])
    assert not any(item['path'] == str(stale) for item in result['top_dirs'])


def test_unreadable_process_is_conservatively_busy(repositories):
    _, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    age_tree(target)
    (proc / '100').mkdir()  # PID still present, inspection failed
    result = module().scan_paths(scan_config(merged), proc=proc)
    assert result['top_dirs'][0]['busy'] is True
    assert result['suggestions'] == []
    assert result['scan_errors']


def test_remote_changed_without_fetch_is_not_claimed_merged(repositories):
    repo, _, unmerged, proc = repositories
    git(unmerged, 'push', 'origin', 'HEAD:refs/heads/feature/test-ci-r1')
    result = module().scan_paths(scan_config(repo), proc=proc)
    assert not any(item['action'] == 'remove_remote_branch' for item in result['suggestions'])


def test_scan_timeout_kills_slow_du_and_returns_unknown(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    du = bin_dir / 'du'
    du.write_text('#!/bin/sh\nexec sleep 60\n')
    du.chmod(0o755)
    cache = tmp_path / '.cache'
    cache.mkdir()
    monkeypatch.setenv('PATH', str(bin_dir) + os.pathsep + os.environ['PATH'])
    start = time.monotonic()
    result = module().scan_bounded(scan_config(cache, top_n=1).__class__(scan_roots=(str(cache),), scan_seconds=1))
    assert time.monotonic() - start < 4
    assert result['scan_errors'] and result['suggestions'] == []


def test_executable_and_symlink_alias_paths_are_busy(repositories, tmp_path):
    _, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    executable = target / 'test'
    executable.write_text('binary')
    alias = tmp_path / 'alias'
    alias.symlink_to(target, target_is_directory=True)
    pid = proc / '100'
    pid.mkdir()
    (pid / 'cwd').symlink_to(proc)
    (pid / 'cmdline').write_bytes(f'cargo\0--target-dir={alias}\0'.encode())
    result = module().scan_paths(scan_config(merged), proc=proc)
    assert result['top_dirs'][0]['busy'] is True
    (pid / 'cmdline').write_bytes(b'custom-argv0\0')
    (pid / 'exe').symlink_to(executable)
    result = module().scan_paths(scan_config(merged), proc=proc)
    assert result['top_dirs'][0]['busy'] is True


def test_merged_worktree_with_recent_target_is_retained(repositories):
    _, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    (target / 'new').write_text('new build between compiler processes')
    result = module().scan_paths(scan_config(merged), proc=proc)
    assert not any(item['action'] == 'remove_worktree' for item in result['suggestions'])


def test_excluding_child_also_preserves_parent_worktree(repositories):
    _, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    age_tree(target)
    result = module().scan_paths(scan_config(merged, excludes=(str(target),)), proc=proc)
    assert not any(item['action'] == 'remove_worktree' for item in result['suggestions'])


def test_bounded_worker_uses_current_package_and_writes_real_sizes(tmp_path):
    cache = tmp_path / '.cache'
    cache.mkdir()
    (cache / 'file').write_bytes(b'x' * 8192)
    result = module().scan_bounded(scan_config(cache))
    assert result['top_dirs'][0]['path'] == str(cache)
    assert result['top_dirs'][0]['size_gb'] >= 8192 / 1024**3


def test_listener_build_config_and_callback_failures_are_isolated(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from paulshaclaw.bot.listener import BotSettings, build_listener
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps({'daemon_name': 'psc', 'default_project': 'demo', 'allowed_user_ids': [7], 'coordinator': {'phase': 'stage1', 'default_payload': {}}, 'pane_assignments': []}))
    monkeypatch.setenv('PSC_SPACE_WARN_GB', '75')
    monkeypatch.setenv('PSC_SPACE_RECOVER_GB', '85')
    monkeypatch.setenv('PSC_SPACE_DISABLED', '1')
    monkeypatch.setenv('PSC_STATE_ROOT', str(tmp_path / 'state'))
    monkeypatch.setenv('PSC_TELEGRAM_BINDINGS_PATH', str(tmp_path / 'bindings.json'))
    monkeypatch.setenv('PSC_MESSAGE_PANE_MAP_PATH', str(tmp_path / 'panes.json'))
    client = Mock()
    client.get_updates.return_value = []
    client.get_my_commands.return_value = []
    client.get_chat_menu_button.return_value = {"type": "commands"}
    listener = build_listener(config_path=str(config_path), settings=BotSettings(token='fake'), client=client)
    alerter = listener.space_alert.__self__
    assert alerter.config.warn_gb == 75 and alerter.config.recover_gb == 85 and alerter.config.disabled
    assert alerter.allowed_user_ids == (7,)
    assert alerter.state_path == tmp_path / 'state' / 'space-monitor.json'
    hooks = []
    listener.cleanup = lambda: None
    listener.queue_alert = lambda: hooks.append('queue')
    listener.mem_alert = lambda: hooks.append('memory')
    listener.space_alert = lambda: (_ for _ in ()).throw(RuntimeError('scan failed'))
    listener.run_once()
    assert hooks == ['queue', 'memory']
    listener.space_alert = lambda: (_ for _ in ()).throw(KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        listener.run_once()


def test_glob_and_symlink_exclusions_preserve_parent_worktree(repositories, tmp_path):
    _, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    age_tree(target)
    alias = tmp_path / 'excluded-alias'
    alias.symlink_to(target, target_is_directory=True)
    for excluded in (str(tmp_path / '*' / 'target'), str(alias)):
        result = module().scan_paths(scan_config(merged, excludes=(excluded,)), proc=proc)
        assert result['top_dirs'] == []
        assert not any(item['action'] == 'remove_worktree' for item in result['suggestions'])


def test_space_in_cmdline_alias_is_still_busy(repositories, tmp_path):
    _, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    age_tree(target)
    alias = tmp_path / 'alias with spaces'
    alias.symlink_to(target, target_is_directory=True)
    pid = proc / '100'
    pid.mkdir()
    (pid / 'cwd').symlink_to(proc)
    (pid / 'cmdline').write_bytes(f'cargo\0--target-dir={alias}\0'.encode())
    result = module().scan_paths(scan_config(merged), proc=proc)
    assert result['top_dirs'][0]['busy'] is True
    assert result['suggestions'] == []


def test_excluded_descendant_preserves_tmp_and_target(repositories, tmp_path):
    _, merged, _, proc = repositories
    target = merged / 'target'
    target.mkdir()
    tmp = tmp_path / 'job-tmp'
    tmp.mkdir()
    for parent in (target, tmp):
        (parent / 'keep').mkdir()
        age_tree(parent)
    result = module().scan_paths(scan_config(target, tmp, excludes=(str(target / 'keep'), str(tmp / 'keep'))), proc=proc)
    assert result['suggestions'] == []
    assert not any(item['reclaimable'] for item in result['top_dirs'])


def test_worker_does_not_load_another_checkout_from_cwd(tmp_path, monkeypatch):
    other = tmp_path / 'other'
    for package in (other / 'paulshaclaw', other / 'paulshaclaw' / 'core'):
        package.mkdir(parents=True, exist_ok=True)
        (package / '__init__.py').write_text('')
    (other / 'paulshaclaw' / 'core' / 'space_pressure_alert.py').write_text('raise RuntimeError("wrong checkout")')
    cache = tmp_path / '.cache'
    cache.mkdir()
    monkeypatch.chdir(other)
    result = module().scan_bounded(scan_config(cache))
    assert result['top_dirs'] and result['top_dirs'][0]['path'] == str(cache)

"""WSL 磁碟容量觀測；只通知與建議，絕不執行回收。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Callable, Mapping, Sequence

from paulshaclaw.config import paths
from paulshaclaw.core.mem_pressure_alert import _AlertSender, _BindingStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpaceConfig:
    warn_gb: int = 100
    critical_gb: int = 50
    recover_gb: int = 120
    interval_seconds: int = 1200
    scan_seconds: int = 10
    top_n: int = 10
    target_idle_hours: int = 24
    tmp_idle_hours: int = 6
    scan_roots: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    merge_target: str = 'origin/main'
    ci_branch_patterns: tuple[str, ...] = ('ci/*', '*-ci-*')
    vhdx_path: str | None = None
    disabled: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'critical_gb', min(self.warn_gb, self.critical_gb))
        object.__setattr__(self, 'recover_gb', max(self.warn_gb, self.recover_gb))


def config_from_env(env: Mapping[str, str] | None = None) -> SpaceConfig:
    env = os.environ if env is None else env
    defaults = SpaceConfig()
    values = {}
    for field in ('warn_gb', 'critical_gb', 'recover_gb', 'interval_seconds', 'scan_seconds', 'top_n', 'target_idle_hours', 'tmp_idle_hours'):
        try:
            value = int(env.get('PSC_SPACE_' + field.upper(), ''))
            values[field] = value if value > 0 else getattr(defaults, field)
        except ValueError:
            values[field] = getattr(defaults, field)
    home = str(paths.home_root())
    default_roots = (f'{home}/prj_pri/*', f'{home}/prj_pri/*-worktrees/*', f'{home}/.cargo', f'{home}/.cache')
    for field, default in (('scan_roots', default_roots), ('excludes', ()), ('ci_branch_patterns', defaults.ci_branch_patterns)):
        raw = env.get('PSC_SPACE_' + field.upper())
        values[field] = tuple(part.strip() for part in raw.split(os.pathsep) if part.strip()) if raw is not None else default
    values['merge_target'] = env.get('PSC_SPACE_MERGE_TARGET', '').strip() or defaults.merge_target
    values['vhdx_path'] = env.get('PSC_SPACE_VHDX_PATH', '').strip() or None
    values['disabled'] = env.get('PSC_SPACE_DISABLED', '').strip() == '1'
    return SpaceConfig(**values)


def parse_df(text: str) -> dict:
    fields = text.strip().splitlines()[-1].split() if text.strip() else []
    if len(fields) != 3 or any(not re.fullmatch(r'\d+G', field) for field in fields):
        raise ValueError('invalid df capacity output')
    avail, used, size = (int(field[:-1]) for field in fields)
    if size <= 0 or avail > size or used > size:
        raise ValueError('invalid df capacity values')
    return {'mount': '/', 'avail_gb': avail, 'used_gb': used, 'size_gb': size, 'use_pct': math.ceil(used * 100 / size)}


def read_root() -> dict:
    import subprocess
    result = subprocess.run(['df', '-BG', '--output=avail,used,size', '/'], capture_output=True, text=True, check=True, timeout=2, env={**os.environ, 'LC_ALL': 'C'})
    return parse_df(result.stdout)


def _vhdx(config: SpaceConfig) -> dict:
    result = {'path': config.vhdx_path, 'size_gb': None, 'note': '未知：未提供可讀取的 vhdx 路徑'}
    if config.vhdx_path:
        try:
            path = Path(config.vhdx_path).expanduser()
            if path.is_file():
                result.update(path=str(path), size_gb=path.stat().st_size / 1024**3, note='Windows 檔案長度；與 ext4 使用量不同')
        except OSError:
            pass
    return result


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.space-', delete=False) as handle:
            temp = Path(handle.name)
            json.dump(state, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


class SpacePressureAlerter:
    def __init__(self, *, sender: _AlertSender, bindings: _BindingStore, allowed_user_ids: Sequence[int], state_path: Path | None = None, config: SpaceConfig | None = None, read_root: Callable | None = None, scan: Callable | None = None, clock: Callable = time.monotonic):
        self.sender = sender
        self.bindings = bindings
        self.allowed_user_ids = tuple(allowed_user_ids)
        self.state_path = state_path or paths.state_path('space-monitor.json')
        self.config = config or config_from_env()
        self._read_root = read_root or globals()['read_root']
        self._scan = scan or (lambda: scan_bounded(self.config))
        self._clock = clock
        self._next_check = 0.0
        self._notified = 0

    @property
    def alerting(self) -> bool:
        return self._notified > 0

    def check_and_alert(self) -> None:
        if self.config.disabled or self._clock() < self._next_check:
            return
        self._next_check = self._clock() + self.config.interval_seconds
        try:
            root = self._read_root()
        except Exception as error:
            logger.error('SPACE_ALERT_READ_ERROR error=%s', error)
            return
        available = root['avail_gb']
        rank = 2 if available < self.config.critical_gb else 1 if available < self.config.warn_gb else 0
        text = None
        if rank > self._notified:
            self._notified = rank
            text = f"{'🚨' if rank == 2 else '⚠️'} 主機磁碟空間{'嚴重不足' if rank == 2 else '偏低'}：/ 可用 {available} GiB"
        elif self.alerting and available >= self.config.recover_gb:
            self._notified = 0
            text = f'✅ 主機磁碟空間已恢復：/ 可用 {available} GiB'
        # ENOSPC 與掃描失敗不得擋住通知。
        if text:
            self._broadcast(text)
        try:
            scan = self._scan()
        except Exception as error:
            scan = {'top_dirs': [], 'suggestions': [], 'scan_errors': [str(error)]}
        state = {
            'checked_at': datetime.now(timezone.utc).isoformat(), 'root': root,
            'vhdx': _vhdx(self.config),
            'thresholds': {key: getattr(self.config, key) for key in ('warn_gb', 'critical_gb', 'recover_gb')},
            'level': ('ok', 'warn', 'critical')[rank], 'alerting': self.alerting,
            **scan, 'auto_reclaim': False,
        }
        try:
            _write_state(self.state_path, state)
        except Exception as error:
            logger.error('SPACE_ALERT_STATE_ERROR error=%s', error)

    def _broadcast(self, text: str) -> None:
        sent = set()
        for user_id in self.allowed_user_ids:
            try:
                chat_id = self.bindings.lookup_chat_id(user_id)
                if chat_id is None or chat_id in sent:
                    continue
                sent.add(chat_id)
                self.sender.send_message(chat_id=chat_id, text=text)
            except Exception as error:
                logger.error('SPACE_ALERT_SEND_ERROR error=%s', error)


class _Scan:
    """Worker 內共用截止時間；外層另以 process group 作硬逾時。"""
    def __init__(self, config: SpaceConfig):
        self.config = config
        self.deadline = time.monotonic() + config.scan_seconds
        self.errors: list[str] = []

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('scan deadline exceeded')
        return remaining

    def run(self, argv: list[str]) -> str:
        import subprocess
        self.remaining()
        result = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=min(2, self.remaining()), env={**os.environ, 'LC_ALL': 'C', 'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'})
        return result.stdout.strip()

    def git(self, repo: Path, *args: str) -> str:
        return self.run(['git', '-C', str(repo), '-c', 'core.fsmonitor=false', *args])

    def clean(self, repo: Path) -> bool:
        return not self.git(repo, 'status', '--porcelain', '--untracked-files=all')

    def ancestor(self, repo: Path, head: str, target: str) -> bool:
        import subprocess
        try:
            self.git(repo, 'merge-base', '--is-ancestor', head, target)
            return True
        except subprocess.CalledProcessError as error:
            if error.returncode != 1:
                raise
            return False


def _within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _processes(proc: Path, scan: _Scan) -> tuple[list[tuple[Path | None, str]], bool]:
    processes = []
    unknown = False
    try:
        with os.scandir(proc) as entries:
            for index, entry in enumerate(entries):
                scan.remaining()
                if index > 32768:
                    raise TimeoutError('process count limit exceeded')
                if not entry.name.isdigit():
                    continue
                pid = Path(entry.path)
                try:
                    # Empty cmdline with no cwd is a kernel thread, not an unknown user process.
                    argv = (pid / 'cmdline').read_bytes().decode(errors='replace').split('\0')
                    cmd = ' '.join(argv).strip()
                    try:
                        cwd = (pid / 'cwd').resolve(strict=True)
                    except FileNotFoundError:
                        if not cmd:
                            continue
                        raise
                    # argv may use a symlink alias or a relative target path.
                    normalized = []
                    for token in argv:
                        token = token.split('=', 1)[-1]
                        if '/' in token:
                            candidate = Path(token)
                            normalized.append(str((candidate if candidate.is_absolute() else cwd / candidate).resolve()))
                    try:
                        normalized.append(str((pid / 'exe').resolve(strict=True)))
                    except FileNotFoundError:
                        pass
                    processes.append((cwd, cmd + ' ' + ' '.join(normalized)))
                except OSError:
                    if pid.exists():
                        unknown = True
    except OSError:
        unknown = True
    if unknown:
        scan.errors.append('process visibility incomplete; busy assumed')
    return processes, unknown


def _busy(path: Path, processes: list[tuple[Path | None, str]], unknown: bool) -> bool:
    if unknown:
        return True
    for cwd, cmd in processes:
        if cwd is not None and _within(cwd, path):
            return True
        # Match a path boundary, including --flag=/path and descendants.
        if re.search(r'(?<![\w/.-])' + re.escape(str(path)) + r'(?=$|[/\s])', cmd):
            return True
        if path.name == 'target' and cwd is not None and _within(cwd, path.parent) and re.search(r'\b(cargo|rustc)\b', cmd):
            return True
    return False


def _exclusions(config: SpaceConfig, scan: _Scan) -> set[Path]:
    import glob
    excluded = set()
    for pattern in config.excludes:
        for match in glob.iglob(os.path.expandvars(os.path.expanduser(pattern))):
            scan.remaining()
            excluded.add(Path(match).resolve())
            if len(excluded) > 256:
                raise TimeoutError('exclusion candidate limit exceeded')
    return excluded


def _discover(config: SpaceConfig, scan: _Scan, excludes: set[Path]) -> list[Path]:
    import glob
    found: set[Path] = set()

    def excluded(path: Path) -> bool:
        return any(_within(path, excluded_path) or _within(excluded_path, path) for excluded_path in excludes)

    for pattern in config.scan_roots:
        for match in glob.iglob(os.path.expandvars(os.path.expanduser(pattern))):
            scan.remaining()
            path = Path(match).resolve()
            if not path.is_dir() or excluded(path):
                continue
            found.add(path)
            if (path / '.git').exists() and (path / 'target').is_dir() and not excluded(path / 'target'):
                found.add(path / 'target')
            if len(found) > 256:
                raise TimeoutError('directory candidate limit exceeded')
    return sorted(found)


def _old_tree(path: Path, hours: int, scan: _Scan) -> bool:
    cutoff = time.time() - hours * 3600
    # Examine descendants; the root mtime alone misses newly written nested artifacts.
    return not scan.run(['find', str(path), '-xdev', '-newermt', f'@{cutoff}', '-print', '-quit'])


def _remote_heads(repo: Path, scan: _Scan) -> dict[str, str]:
    heads = {}
    for line in scan.git(repo, 'ls-remote', '--heads', 'origin').splitlines():
        oid, ref = line.split()
        if ref.startswith('refs/heads/'):
            heads[ref.removeprefix('refs/heads/')] = oid
    return heads


def scan_paths(config: SpaceConfig, *, proc: Path = Path('/proc')) -> dict:
    """唯讀掃描；任何未完成的整體掃描不產生回收建議。"""
    import fnmatch
    scan = _Scan(config)
    top = []
    suggestions = []
    try:
        excludes = _exclusions(config, scan)
        candidates = _discover(config, scan, excludes)
        processes, unknown = _processes(proc, scan)
        repositories = {p for p in candidates if (p / '.git').exists()}
        repositories.update(p.parent for p in candidates if p.name == 'target' and (p.parent / '.git').exists())
        git_info = {}
        remote_cache = {}
        for repo in sorted(repositories):
            try:
                common = scan.git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')
                if common not in remote_cache:
                    remote_cache[common] = _remote_heads(repo, scan)
                heads = remote_cache[common]
                target = scan.git(repo, 'rev-parse', '--verify', config.merge_target + '^{commit}')
                if config.merge_target.startswith('origin/') and heads.get(config.merge_target.removeprefix('origin/')) != target:
                    raise ValueError('remote target changed or unavailable; fetch before considering suggestions')
                clean = scan.clean(repo)
                busy = _busy(repo, processes, unknown)
                branch = scan.git(repo, 'branch', '--show-current')
                head = scan.git(repo, 'rev-parse', 'HEAD')
                linked = (repo / '.git').is_file()
                git_info[repo] = (clean, busy, linked)
                protected_child = any(_within(excluded_path, repo) for excluded_path in excludes)
                target_idle = not (repo / 'target').exists() or _old_tree(repo / 'target', config.target_idle_hours, scan)
                if linked and branch and clean and not busy and not protected_child and target_idle and scan.ancestor(repo, head, target):
                    # Locked worktrees are explicitly retained by their owner.
                    records = scan.git(repo, 'worktree', 'list', '--porcelain').split('\n\n')
                    record = next((r for r in records if r.splitlines()[0] == f'worktree {repo}'), '')
                    if record and not any(line.startswith(('locked', 'prunable')) for line in record.splitlines()):
                        suggestions.append({'action': 'remove_worktree', 'path': str(repo), 'branch': branch, 'reason': f'乾淨且 HEAD 已合併至 {config.merge_target}；未觀察到使用中行程'})
            except Exception as error:
                scan.errors.append(f'git {repo}: {type(error).__name__}')
        for path in candidates:
            scan.remaining()
            if path in repositories or path.name.endswith('-worktrees'):
                continue
            kind = 'cargo_target' if path.name == 'target' else 'temporary' if path.name.endswith('-tmp') else 'cache'
            busy = _busy(path, processes, unknown)
            if path.name == 'target' and path.parent in git_info:
                busy = busy or git_info[path.parent][1]
            size = int(scan.run(['du', '-s', '-B1', '--', str(path)]).split()[0]) / 1024**3
            item = {'path': str(path), 'size_gb': size, 'kind': kind, 'busy': busy, 'reclaimable': False}
            top.append(item)
            if busy:
                continue
            if kind == 'cargo_target' and path.parent in git_info:
                clean, _, linked = git_info[path.parent]
                # 主 repo 的 target 保留；只有乾淨 linked worktree 的閒置 target 才建議。
                if clean and linked and _old_tree(path, config.target_idle_hours, scan):
                    item['reclaimable'] = True
                    suggestions.append({'action': 'remove_target', 'path': str(path), 'reason': f'乾淨 worktree，所有內容超過 {config.target_idle_hours} 小時未修改，未觀察到使用中行程'})
            elif kind == 'temporary' and _old_tree(path, config.tmp_idle_hours, scan):
                item['reclaimable'] = True
                suggestions.append({'action': 'remove_tmp', 'path': str(path), 'reason': f'所有內容超過 {config.tmp_idle_hours} 小時未修改，未觀察到使用中行程'})
        seen = set()
        for repo in sorted(git_info):
            if git_info[repo][1]:
                continue
            common = scan.git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')
            if common in seen:
                continue
            seen.add(common)
            for branch, head in remote_cache[common].items():
                if not any(fnmatch.fnmatchcase(branch, pattern) for pattern in config.ci_branch_patterns):
                    continue
                if 'origin/' + branch == config.merge_target:
                    continue
                if scan.ancestor(repo, head, config.merge_target):
                    suggestions.append({'action': 'remove_remote_branch', 'path': str(repo), 'remote': 'origin', 'branch': branch, 'head': head, 'reason': f'即時遠端 HEAD 已合併至 {config.merge_target}；符合一次性 CI 分支樣式'})
    except Exception as error:
        scan.errors.append(f'scan incomplete: {type(error).__name__}')
    if scan.errors:
        suggestions = []
        for item in top:
            item['reclaimable'] = False
    order = {'remove_worktree': 0, 'remove_target': 1, 'remove_tmp': 2, 'remove_remote_branch': 3}
    return {'top_dirs': sorted(top, key=lambda item: item['size_gb'], reverse=True)[:config.top_n], 'suggestions': sorted(suggestions, key=lambda item: order[item['action']]), 'scan_errors': scan.errors}


def scan_bounded(config: SpaceConfig) -> dict:
    """Hard deadline covers discovery, /proc, Git, du, and every descendant process."""
    import signal
    import subprocess
    import sys
    # -m alone searches cwd first and can silently run an older checkout.
    entry = 'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module("paulshaclaw.core.space_pressure_alert",run_name="__main__")'
    package_root = str(Path(__file__).resolve().parents[2])
    worker = subprocess.Popen([sys.executable, '-c', entry, package_root, '--scan'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, _ = worker.communicate(json.dumps(asdict(config)), timeout=config.scan_seconds)
        if worker.returncode:
            raise RuntimeError('scan worker failed')
        return json.loads(stdout)
    except Exception as error:
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        worker.communicate()
        return {'top_dirs': [], 'suggestions': [], 'scan_errors': [f'scan incomplete: {type(error).__name__}']}


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--scan']:
        print(json.dumps(scan_paths(SpaceConfig(**json.load(sys.stdin)))))

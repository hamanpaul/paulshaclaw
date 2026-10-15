"""Work-pane summaries identify foreground agents without per-pane process scans."""

from dataclasses import replace
import subprocess

import pytest

from paulshaclaw.cockpit.models import PaneRecord
from paulshaclaw.cockpit.tmux import TmuxClient, derive_summary


def pane(command: str, *, title: str = "host") -> PaneRecord:
    return PaneRecord(
        pane_id="%1", session_name="main", window_index="0", title=title,
        command=command, left=0, top=0, width=80, height=24, active=False,
        pane_tty="/dev/pts/1", pane_current_path="/projects/repo", host_short="host",
    )


@pytest.mark.parametrize("agent", ["codex", "copilot", "pi", "agy", "claude"])
def test_direct_agent_keeps_identity_before_directory_or_task(agent):
    # Losing direct-command detection would hide the agent behind cwd/title again.
    assert derive_summary(pane(agent), {}) == f"[{agent}] repo"
    assert derive_summary(pane(agent, title="review changes"), {}) == f"[{agent}] review changes"
    assert derive_summary(replace(pane(agent), pane_current_path=""), {}) == f"[{agent}]"


def scan(monkeypatch, processes, *, command="bash", title="host", count=1):
    raw = "".join(
        f"%{index}\tmain\t0\t{title}\t{command}\t0\t0\t80\t24\t0\t/dev/pts/{index}\t/projects/repo\thost\n"
        for index in range(1, count + 1)
    )
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[:3] == ["tmux", "list-panes", "-a"]:
            return subprocess.CompletedProcess(argv, 0, stdout=raw)
        assert argv[0] == "ps"
        assert kwargs["timeout"] <= 1
        assert kwargs["errors"] == "replace"
        if isinstance(processes, Exception):
            raise processes
        return subprocess.CompletedProcess(argv, 0, stdout=processes)

    monkeypatch.setattr("paulshaclaw.cockpit.tmux.subprocess.run", run)
    result = TmuxClient().list_panes(cockpit_pane_id="%0")
    assert len(calls) == 2  # One tmux and one bounded process scan, even for many panes.
    return result


@pytest.mark.parametrize(("args", "agent"), [
    ("/opt/codex/vendor/linux/codex/codex", "codex"),
    ("node /usr/lib/node_modules/@openai/codex/bin/codex.js", "codex"),
    ("node /usr/lib/node_modules/@github/copilot/index.js", "copilot"),
    ("node /usr/lib/node_modules/@mariozechner/pi-coding-agent/dist/cli.js", "pi"),
    ("/opt/bin/agy", "agy"),
    ("node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js", "claude"),
])
@pytest.mark.parametrize("command", ["bash", "node", "python"])
def test_wrapped_agent_comes_from_foreground_process_group(monkeypatch, args, agent, command):
    processes = f"pts/1 100 200 -bash\npts/1 200 200 {args}\n"
    panes = scan(monkeypatch, processes, command=command)
    assert panes[0].summary == f"[{agent}] repo"


def test_batch_scan_preserves_minicom_and_isolates_agents_by_tty(monkeypatch):
    processes = (
        "pts/1 100 100 codex\n"
        "pts/2 200 200 copilot\n"
        "pts/3 300 300 minicom -D /dev/ttyUSB0 -C /logs/mini_COM0.log\n"
    )
    panes = scan(monkeypatch, processes, count=20)
    assert [p.summary for p in panes[:4]] == ["[codex] repo", "[copilot] repo", "minicom COM0", "repo"]


@pytest.mark.parametrize("processes", [
    "pts/1 100 200 codex\npts/1 200 200 vim README.md\n",  # background agent
    "pts/1 100 -1 codex\n",  # no foreground process group
    "? 100 100 codex\n",  # detached process
    "pts/1 invalid invalid codex\n",  # malformed ps record
    "pts/1 100 100 man codex\n",
    "pts/1 100 100 vim /usr/lib/node_modules/@github/copilot/index.js\n",
    "pts/1 100 100 node unrelated.js codex\n",
    "pts/1 100 100 bash -c codex\n",  # shell argv alone does not prove a running agent
    "pts/1 100 100 node -e codex\n",
    "pts/1 100 100 python report.py --agent copilot\n",
])
def test_background_and_argument_mentions_do_not_mark_pane_as_agent(monkeypatch, processes):
    assert scan(monkeypatch, processes)[0].summary == "repo"


def test_process_scan_failure_preserves_direct_agent_badge(monkeypatch):
    panes = scan(monkeypatch, subprocess.TimeoutExpired("ps", 1), command="agy")
    assert panes[0].summary == "[agy] repo"


def test_agent_title_preserves_task_without_repeating_badge(monkeypatch):
    panes = scan(monkeypatch, "pts/1 100 100 codex\n", title="[codex] review changes")
    assert panes[0].summary == "[codex] review changes"


@pytest.mark.parametrize("options", [
    "--enable-source-maps", "--", "--require bootstrap.js",
    "--import=bootstrap", "--max-old-space-size=4096", "--inspect=localhost:9229",
])
def test_node_options_do_not_hide_agent_entrypoint(monkeypatch, options):
    processes = f"pts/1 100 100 node {options} /usr/lib/node_modules/@github/copilot/index.js\n"
    assert scan(monkeypatch, processes)[0].summary == "[copilot] repo"


@pytest.mark.parametrize("args", [
    "node -e /usr/lib/node_modules/@github/copilot/index.js",
    "node --eval=/usr/lib/node_modules/@github/copilot/index.js",
    "node -p /usr/lib/node_modules/@github/copilot/index.js",
    "node --require /usr/lib/node_modules/@github/copilot/index.js report.js",
    "node --title copilot report.js",
])
def test_node_option_values_are_not_agent_entrypoints(monkeypatch, args):
    assert scan(monkeypatch, f"pts/1 100 100 {args}\n")[0].summary == "repo"

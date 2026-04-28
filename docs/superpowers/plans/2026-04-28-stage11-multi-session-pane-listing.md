# Stage 11 Multi-Session Pane Listing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Stage 11 cockpit list panes from all local tmux sessions while keeping active-slot semantics scoped to the cockpit session.

**Architecture:** Extend the pane data model with session/window metadata, let the tmux adapter use `list-panes -a`, and thread `cockpit_session_name` through the state store and app startup. The UI remains a flat pane list, while `Enter` keeps using the existing layout action service because tmux pane IDs are globally unique within the server.

**Tech Stack:** Python standard library, `unittest`, `unittest.mock`, tmux CLI, optional `textual==0.61.1` from `requirements-stage11.txt`, OpenSpec change `openspec/changes/stage11-multi-session-pane-listing/`.

---

## Execution Notes

- Primary implementation/review model: `gpt-5.3-codex`.
- Do not edit `scripts/start.sh`.
- Do not change `LayoutActionService` behavior or its public method names.
- Keep generated code and tests focused on Stage 11 files.
- Run commands from `/home/paul_chen/prj_pri/paulshaclaw`.

## File Structure

- Modify: `paulshaclaw/cockpit/models.py`
  - Add `session_name` and `window_index` to `PaneRecord`.
- Modify: `paulshaclaw/cockpit/tmux.py`
  - Use `tmux list-panes -a`, parse 9/10 column rows, and preserve session/window metadata during preview enrichment.
- Modify: `paulshaclaw/cockpit/store.py`
  - Add `cockpit_session_name`, scope active-slot logic to that session, and sort candidates.
- Modify: `paulshaclaw/cockpit/app.py`
  - Accept `cockpit_session_name`, add display label helper, update footer binding descriptions, and open help modal.
- Create: `paulshaclaw/cockpit/help.py`
  - Define `HelpModal` with binding text and multi-session behavior notes.
- Modify: `paulshaclaw/cockpit/__main__.py`
  - Derive `cockpit_session_name` from the cockpit pane record before constructing the app.
- Modify: `tests/test_stage11_operator_cockpit.py`
  - Update fixtures and add parser, store, startup, label, and help tests.
- Modify: `tests/test_stage11_operator_cockpit_e2e.py`
  - Remove `TmuxClient(session_name=...)`, keep real tmux test isolated to its generated session, and add fake multi-session candidate smoke coverage.

### Task 1: Pane Model And Tmux Parser

**Files:**
- Modify: `tests/test_stage11_operator_cockpit.py`
- Modify: `paulshaclaw/cockpit/models.py`
- Modify: `paulshaclaw/cockpit/tmux.py`

- [ ] **Step 1: Add a shared test fixture helper**

Add this helper after the imports in `tests/test_stage11_operator_cockpit.py`:

```python
def pane_record(
    pane_id: str,
    *,
    session_name: str = "main",
    window_index: str = "0",
    title: str = "pane",
    command: str = "bash",
    left: int = 0,
    top: int = 0,
    width: int = 80,
    height: int = 24,
    active: bool = False,
    preview: tuple[str, ...] = (),
) -> PaneRecord:
    return PaneRecord(
        pane_id=pane_id,
        session_name=session_name,
        window_index=window_index,
        title=title,
        command=command,
        left=left,
        top=top,
        width=width,
        height=height,
        active=active,
        preview=preview,
    )
```

- [ ] **Step 2: Replace parser tests and add list command coverage**

Replace the three parser/tmux tests in `Stage11StateTests` with this block:

```python
    def test_parse_list_panes_extracts_geometry(self) -> None:
        raw = "%0\tmain\t0\tcockpit\tpython\t0\t0\t120\t40\n%4\tmain\t1\tssh\tbash\t120\t0\t120\t40\n"
        panes = parse_list_panes(raw)

        self.assertEqual(panes[0].pane_id, "%0")
        self.assertEqual(panes[0].session_name, "main")
        self.assertEqual(panes[0].window_index, "0")
        self.assertEqual(panes[1].left, 120)
        self.assertEqual(panes[1].width, 120)

    def test_parse_list_panes_skips_malformed_numeric_fields(self) -> None:
        raw = "%0\tmain\t0\tcockpit\tpython\t0\t0\t120\t40\n%4\tmain\t1\tssh\tbash\tnan\t0\t120\t40\n"
        panes = parse_list_panes(raw)

        self.assertEqual([pane.pane_id for pane in panes], ["%0"])

    def test_parse_list_panes_extracts_session_window(self) -> None:
        raw = (
            "%1\tmain\t0\tserver\tbash\t0\t0\t100\t40\t1\n"
            "%9\twork\t2\tpytest\tpython\t100\t0\t100\t40\t0\n"
        )
        panes = parse_list_panes(raw)

        self.assertEqual([(pane.pane_id, pane.session_name, pane.window_index) for pane in panes], [
            ("%1", "main", "0"),
            ("%9", "work", "2"),
        ])
        self.assertTrue(panes[0].active)
        self.assertFalse(panes[1].active)

    def test_list_panes_uses_dash_a_flag(self) -> None:
        client = TmuxClient()
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="%0\tmain\t0\tcockpit\tpython\t0\t0\t120\t40\t1\n",
        )
        with patch("paulshaclaw.cockpit.tmux.subprocess.run", return_value=completed) as run_mock:
            panes = client.list_panes(cockpit_pane_id="%0")

        command = run_mock.call_args.args[0]
        self.assertEqual(command[:3], ["tmux", "list-panes", "-a"])
        self.assertNotIn("-t", command)
        self.assertIn("#{session_name}", command[-1])
        self.assertIn("#{window_index}", command[-1])
        self.assertEqual(panes[0].session_name, "main")
```

- [ ] **Step 3: Run the focused parser tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_parse_list_panes_extracts_geometry tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_list_panes_uses_dash_a_flag -v
```

Expected: FAIL with `TypeError: PaneRecord.__init__() got an unexpected keyword argument 'session_name'` or an assertion showing the command does not include `-a`.

- [ ] **Step 4: Update `PaneRecord`**

Replace the `PaneRecord` dataclass in `paulshaclaw/cockpit/models.py` with:

```python
@dataclass(frozen=True)
class PaneRecord:
    pane_id: str
    session_name: str
    window_index: str
    title: str
    command: str
    left: int
    top: int
    width: int
    height: int
    active: bool
    preview: tuple[str, ...]

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def anchor(self) -> SlotAnchor:
        return SlotAnchor(
            left=self.left,
            top=self.top,
            width=self.width,
            height=self.height,
        )
```

- [ ] **Step 5: Update `tmux.py`**

Replace `LIST_PANES_FORMAT`, `parse_list_panes()`, and `TmuxClient` in `paulshaclaw/cockpit/tmux.py` with:

```python
LIST_PANES_FORMAT = "\t".join(
    [
        "#{pane_id}",
        "#{session_name}",
        "#{window_index}",
        "#{pane_title}",
        "#{pane_current_command}",
        "#{pane_left}",
        "#{pane_top}",
        "#{pane_width}",
        "#{pane_height}",
        "#{pane_active}",
    ]
)


def parse_list_panes(raw: str) -> tuple[PaneRecord, ...]:
    panes: list[PaneRecord] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 9:
            pane_id, session_name, window_index, title, command, left, top, width, height = parts
            active = "0"
        elif len(parts) == 10:
            pane_id, session_name, window_index, title, command, left, top, width, height, active = parts
        else:
            continue
        try:
            left_value = int(left)
            top_value = int(top)
            width_value = int(width)
            height_value = int(height)
        except ValueError:
            continue
        panes.append(
            PaneRecord(
                pane_id=pane_id,
                session_name=session_name,
                window_index=window_index,
                title=title,
                command=command,
                left=left_value,
                top=top_value,
                width=width_value,
                height=height_value,
                active=active == "1",
                preview=(),
            )
        )
    return tuple(panes)


class TmuxClient:
    def list_panes(self, *, cockpit_pane_id: str) -> tuple[PaneRecord, ...]:
        try:
            completed = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", LIST_PANES_FORMAT],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ()
        panes = parse_list_panes(completed.stdout)
        enriched: list[PaneRecord] = []
        for pane in panes:
            preview = ()
            if pane.pane_id != cockpit_pane_id:
                try:
                    preview = self.capture_preview(pane.pane_id)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    preview = ()
            enriched.append(
                PaneRecord(
                    pane_id=pane.pane_id,
                    session_name=pane.session_name,
                    window_index=pane.window_index,
                    title=pane.title,
                    command=pane.command,
                    left=pane.left,
                    top=pane.top,
                    width=pane.width,
                    height=pane.height,
                    active=pane.active,
                    preview=preview,
                )
            )
        return tuple(enriched)

    def capture_preview(self, pane_id: str, *, lines: int = 20) -> tuple[str, ...]:
        completed = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return tuple(line.rstrip() for line in completed.stdout.splitlines() if line.strip())
```

- [ ] **Step 6: Run the parser tests and commit**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_parse_list_panes_extracts_geometry tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_parse_list_panes_skips_malformed_numeric_fields tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_parse_list_panes_extracts_session_window tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_list_panes_uses_dash_a_flag -v
```

Expected: PASS for all four tests.

Commit:

```bash
git add paulshaclaw/cockpit/models.py paulshaclaw/cockpit/tmux.py tests/test_stage11_operator_cockpit.py
git commit -m "feat: scan tmux panes across sessions"
```

### Task 2: Cockpit State Session Semantics

**Files:**
- Modify: `tests/test_stage11_operator_cockpit.py`
- Modify: `paulshaclaw/cockpit/store.py`

- [ ] **Step 1: Replace state tests with session-aware coverage**

In `tests/test_stage11_operator_cockpit.py`, replace the existing startup slot and state segmentation tests with:

```python
    def test_choose_startup_slot_excludes_cockpit_even_when_same_size(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", title="agent1", command="node", left=0, top=40, width=80, height=20),
        )

        anchor = choose_startup_slot(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual(anchor, SlotAnchor(left=120, top=0, width=120, height=40))

    def test_choose_startup_slot_only_considers_cockpit_session(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%9", session_name="work", title="huge", left=0, top=0, width=300, height=80),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
        )

        anchor = choose_startup_slot(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual(anchor, SlotAnchor(left=120, top=0, width=120, height=40))

    def test_state_segments_active_and_candidate_sections(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", title="agent1", command="node", left=0, top=40, width=80, height=20),
            pane_record("%2", title="iperf", command="iperf3", left=80, top=40, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual([pane.pane_id for pane in state.active_section], ["%4"])
        self.assertEqual([pane.pane_id for pane in state.candidate_section], ["%1", "%2"])

    def test_active_section_excludes_other_sessions_with_same_anchor(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%4", title="active", left=120, top=0, width=120, height=40),
            pane_record("%9", session_name="work", title="collision", left=120, top=0, width=120, height=40),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual([pane.pane_id for pane in state.active_section], ["%4"])
        self.assertIn("%9", [pane.pane_id for pane in state.candidate_section])

    def test_candidate_section_sorted_by_session_window_pane(self) -> None:
        panes = (
            pane_record("%0", session_name="main", window_index="0", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", window_index="0", left=120, top=0, width=120, height=40),
            pane_record("%7", session_name="beta", window_index="2", left=0, top=0, width=80, height=20),
            pane_record("%3", session_name="alpha", window_index="1", left=0, top=0, width=80, height=20),
            pane_record("%2", session_name="beta", window_index="1", left=0, top=0, width=80, height=20),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        self.assertEqual([pane.pane_id for pane in state.candidate_section], ["%3", "%2", "%7"])

    def test_refresh_active_lost_only_when_cockpit_session_pane_gone(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%4", title="active", left=120, top=0, width=120, height=40),
            pane_record("%9", session_name="work", title="remote", left=120, top=0, width=120, height=40),
        )
        state = CockpitState.from_panes(panes, cockpit_pane_id="%0", cockpit_session_name="main")

        stable = state.refresh((
            pane_record("%0", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%4", title="active", left=120, top=0, width=120, height=40),
        ))
        self.assertIsNone(stable.degraded_reason)

        lost = state.refresh((
            pane_record("%0", title="cockpit", left=0, top=0, width=120, height=40),
            pane_record("%9", session_name="work", title="collision", left=120, top=0, width=120, height=40),
        ))
        self.assertEqual(lost.degraded_reason, "active-slot-lost")
        self.assertEqual(lost.active_section, ())
```

- [ ] **Step 2: Run state tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py::Stage11StateTests -v
```

Expected: FAIL with missing `cockpit_session_name` parameters and session filtering assertions.

- [ ] **Step 3: Replace `store.py` with session-aware state logic**

Replace the body of `paulshaclaw/cockpit/store.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass

from .models import PaneRecord, SlotAnchor


def choose_startup_slot(
    panes: tuple[PaneRecord, ...],
    *,
    cockpit_pane_id: str,
    cockpit_session_name: str,
) -> SlotAnchor:
    candidates = tuple(
        pane
        for pane in panes
        if pane.pane_id != cockpit_pane_id and pane.session_name == cockpit_session_name
    )
    if not candidates:
        raise ValueError("no non-cockpit panes available for Stage 11 active slot")
    winner = max(candidates, key=lambda pane: (pane.area, pane.width, pane.height, pane.pane_id))
    return winner.anchor


@dataclass(frozen=True)
class CockpitState:
    cockpit_pane_id: str
    cockpit_session_name: str
    slot_anchor: SlotAnchor
    panes: tuple[PaneRecord, ...]
    selected_index: int
    degraded_reason: str | None

    @classmethod
    def from_panes(
        cls,
        panes: tuple[PaneRecord, ...],
        *,
        cockpit_pane_id: str,
        cockpit_session_name: str,
    ) -> "CockpitState":
        return cls(
            cockpit_pane_id=cockpit_pane_id,
            cockpit_session_name=cockpit_session_name,
            slot_anchor=choose_startup_slot(
                panes,
                cockpit_pane_id=cockpit_pane_id,
                cockpit_session_name=cockpit_session_name,
            ),
            panes=panes,
            selected_index=0,
            degraded_reason=None,
        )

    def _is_active_slot_pane(self, pane: PaneRecord) -> bool:
        return (
            pane.pane_id != self.cockpit_pane_id
            and pane.session_name == self.cockpit_session_name
            and pane.anchor == self.slot_anchor
        )

    @property
    def active_section(self) -> tuple[PaneRecord, ...]:
        return tuple(pane for pane in self.panes if self._is_active_slot_pane(pane))

    @property
    def candidate_section(self) -> tuple[PaneRecord, ...]:
        candidates = (
            pane
            for pane in self.panes
            if pane.pane_id != self.cockpit_pane_id and not self._is_active_slot_pane(pane)
        )
        return tuple(sorted(candidates, key=lambda pane: (pane.session_name, pane.window_index, pane.pane_id)))

    @property
    def active_pane(self) -> PaneRecord | None:
        for pane in self.active_section:
            return pane
        return None

    @property
    def selected_pane(self) -> PaneRecord | None:
        if not self.candidate_section:
            return None
        clamped = min(self.selected_index, len(self.candidate_section) - 1)
        return self.candidate_section[clamped]

    def move_selection(self, delta: int) -> "CockpitState":
        if not self.candidate_section:
            return self
        count = len(self.candidate_section)
        next_index = (self.selected_index + delta) % count
        return CockpitState(
            cockpit_pane_id=self.cockpit_pane_id,
            cockpit_session_name=self.cockpit_session_name,
            slot_anchor=self.slot_anchor,
            panes=self.panes,
            selected_index=next_index,
            degraded_reason=self.degraded_reason,
        )

    def refresh(self, panes: tuple[PaneRecord, ...]) -> "CockpitState":
        refreshed = CockpitState(
            cockpit_pane_id=self.cockpit_pane_id,
            cockpit_session_name=self.cockpit_session_name,
            slot_anchor=self.slot_anchor,
            panes=panes,
            selected_index=self.selected_index,
            degraded_reason=None,
        )
        candidate_count = len(refreshed.candidate_section)
        next_index = self.selected_index
        if candidate_count == 0:
            next_index = 0
        elif next_index >= candidate_count:
            next_index = candidate_count - 1
        active_exists = refreshed.active_pane is not None
        return CockpitState(
            cockpit_pane_id=self.cockpit_pane_id,
            cockpit_session_name=self.cockpit_session_name,
            slot_anchor=self.slot_anchor,
            panes=panes,
            selected_index=next_index,
            degraded_reason=None if active_exists else "active-slot-lost",
        )
```

- [ ] **Step 4: Run state tests and commit**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py::Stage11StateTests -v
```

Expected: PASS for all state tests.

Commit:

```bash
git add paulshaclaw/cockpit/store.py tests/test_stage11_operator_cockpit.py
git commit -m "feat: scope cockpit active slot by session"
```

### Task 3: Startup Derivation And Pane Labels

**Files:**
- Modify: `tests/test_stage11_operator_cockpit.py`
- Modify: `paulshaclaw/cockpit/app.py`
- Modify: `paulshaclaw/cockpit/__main__.py`

- [ ] **Step 1: Add startup derivation and label tests**

Update the `app` import in `tests/test_stage11_operator_cockpit.py`:

```python
from paulshaclaw.cockpit.app import CockpitApp, pane_display_label
```

Add this helper class near `FakeLayoutActionService`:

```python
class DummyCockpitApp:
    def run(self) -> None:
        return None
```

Add these tests:

```python
    def test_main_derives_cockpit_session_from_pane_record(self) -> None:
        panes = (
            pane_record("%0", session_name="main", title="cockpit", command="python", width=120, height=40),
            pane_record("%4", session_name="main", title="ssh", command="bash", left=120, width=120, height=40),
            pane_record("%9", session_name="work", title="pytest", command="python", width=80, height=20),
        )
        with (
            patch.object(TmuxClient, "list_panes", return_value=panes),
            patch("paulshaclaw.cockpit.__main__.ArtifactAdapter") as adapter_class,
            patch.object(CockpitApp, "from_snapshot", return_value=DummyCockpitApp()) as from_snapshot,
        ):
            adapter_class.return_value.load_jobs_by_pane.return_value = {}
            exit_code = cockpit_main.main(["--cockpit-pane", "%0"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(from_snapshot.call_args.kwargs["cockpit_session_name"], "main")

    def test_pane_display_label_includes_session_window(self) -> None:
        pane = pane_record("%12", session_name="work", window_index="2", title="pytest")

        self.assertEqual(pane_display_label(pane), "work:2 %12 pytest")
```

Keep `test_main_exits_with_error_when_cockpit_pane_is_missing` and update its patched pane records only if needed.

- [ ] **Step 2: Run startup/label tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py::Stage11CliTests::test_main_derives_cockpit_session_from_pane_record tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_pane_display_label_includes_session_window -v
```

Expected: FAIL with `ImportError` for `pane_display_label` or missing `cockpit_session_name`.

- [ ] **Step 3: Add `pane_display_label()` and thread `cockpit_session_name` through `CockpitApp`**

In `paulshaclaw/cockpit/app.py`, add this helper after imports:

```python
def pane_display_label(pane: PaneRecord) -> str:
    return f"{pane.session_name}:{pane.window_index} {pane.pane_id} {pane.title}"
```

Update `CockpitApp.from_snapshot()` to accept and pass `cockpit_session_name`:

```python
    @classmethod
    def from_snapshot(
        cls,
        *,
        panes: tuple[PaneRecord, ...],
        cockpit_pane_id: str,
        cockpit_session_name: str,
        jobs_by_pane: dict[str, tuple[JobSummary, ...]],
        actions: LayoutActionService,
        pane_loader: Callable[..., tuple[PaneRecord, ...]] | None = None,
    ) -> "CockpitApp":
        return cls(
            state=CockpitState.from_panes(
                panes,
                cockpit_pane_id=cockpit_pane_id,
                cockpit_session_name=cockpit_session_name,
            ),
            jobs_by_pane=jobs_by_pane,
            actions=actions,
            pane_loader=pane_loader,
        )
```

Update `_refresh_widgets()` label construction:

```python
        active = self.state.active_pane
        active_text = (
            "<missing>"
            if active is None
            else f"ACTIVE {pane_display_label(active)} {active.command}"
        )
        self.query_one("#active-slot", Static).update(active_text)

        work_list = self.query_one("#work-list", ListView)
        work_list.clear()
        if active is not None:
            work_list.append(ListItem(Static(f"[ACTIVE] {pane_display_label(active)}")))
        for pane in self.state.candidate_section:
            prefix = ">" if self.state.selected_pane and pane.pane_id == self.state.selected_pane.pane_id else " "
            work_list.append(ListItem(Static(f"{prefix} {pane_display_label(pane)}")))
```

- [ ] **Step 4: Derive cockpit session in `__main__.py`**

In `paulshaclaw/cockpit/__main__.py`, replace the block after loading `jobs_by_pane` with:

```python
    cockpit_pane = next((pane for pane in panes if pane.pane_id == args.cockpit_pane), None)
    if cockpit_pane is None:
        print(f"cockpit pane not found: {args.cockpit_pane}", file=sys.stderr)
        return 1
    if args.once:
        return 0
    app = CockpitApp.from_snapshot(
        panes=panes,
        cockpit_pane_id=args.cockpit_pane,
        cockpit_session_name=cockpit_pane.session_name,
        jobs_by_pane=jobs_by_pane,
        actions=LayoutActionService(),
        pane_loader=tmux_client.list_panes,
    )
```

- [ ] **Step 5: Update existing app tests to pass `cockpit_session_name`**

For each `CockpitApp.from_snapshot(...)` call in `tests/test_stage11_operator_cockpit.py`, add:

```python
            cockpit_session_name="main",
```

Replace each direct `PaneRecord(...)` call in `Stage11AppTests` with `pane_record(...)`, preserving `pane_id`, `title`, `command`, geometry, and `preview` values.

- [ ] **Step 6: Run startup/app tests and commit**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py::Stage11CliTests tests/test_stage11_operator_cockpit.py::Stage11AppTests -v
```

Expected: PASS, or SKIPPED for `Stage11AppTests` only when Textual is unavailable in the active environment.

Commit:

```bash
git add paulshaclaw/cockpit/app.py paulshaclaw/cockpit/__main__.py tests/test_stage11_operator_cockpit.py
git commit -m "feat: derive cockpit session for stage11 startup"
```

### Task 4: Hotkey Help Modal

**Files:**
- Modify: `tests/test_stage11_operator_cockpit.py`
- Modify: `paulshaclaw/cockpit/app.py`
- Create: `paulshaclaw/cockpit/help.py`

- [ ] **Step 1: Add help modal tests**

Add this import:

```python
from paulshaclaw.cockpit.help import HelpModal
```

Add this non-Textual test to `Stage11StateTests`:

```python
    def test_help_modal_lists_all_bindings(self) -> None:
        help_text = HelpModal.render_help_text(CockpitApp.BINDINGS)

        self.assertIn("up: ↑/↓ 選擇", help_text)
        self.assertIn("down: ↑/↓ 選擇", help_text)
        self.assertIn("enter: Enter 把選中的 pane 換到我面前", help_text)
        self.assertIn("c: c 回 cockpit", help_text)
        self.assertIn("question_mark: ? 顯示說明", help_text)
        self.assertIn("all local tmux sessions", help_text)
```

Add these Textual tests to `Stage11AppTests`:

```python
    async def test_question_mark_opens_help_modal(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", title="agent1", command="node", left=0, top=40, width=80, height=20),
        )
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )

        async with app.run_test() as pilot:
            await pilot.press("?")
            self.assertIsInstance(app.screen, HelpModal)

    async def test_help_modal_dismisses_on_escape(self) -> None:
        panes = (
            pane_record("%0", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", title="ssh", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%1", title="agent1", command="node", left=0, top=40, width=80, height=20),
        )
        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=FakeLayoutActionService(),
        )

        async with app.run_test() as pilot:
            await pilot.press("?")
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, HelpModal)
```

- [ ] **Step 2: Run help tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_help_modal_lists_all_bindings tests/test_stage11_operator_cockpit.py::Stage11AppTests::test_question_mark_opens_help_modal tests/test_stage11_operator_cockpit.py::Stage11AppTests::test_help_modal_dismisses_on_escape -v
```

Expected: FAIL with `ModuleNotFoundError` for `paulshaclaw.cockpit.help` or missing `show_help`.

- [ ] **Step 3: Create `help.py`**

Create `paulshaclaw/cockpit/help.py`:

```python
from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.screen import ModalScreen
    from textual.widgets import Static
except Exception:  # pragma: no cover - fallback when textual not installed
    from typing import Any, Generic, Iterable, TypeVar

    T = TypeVar("T")
    ComposeResult = Iterable[Any]

    class Binding:  # pragma: no cover - noop
        def __init__(self, key: str, handler: str, description: str) -> None:
            self.key = key
            self.handler = handler
            self.description = description

    class ModalScreen(Generic[T]):  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dismiss(self) -> None:
            pass

    class Static:  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass


class HelpModal(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss_help", "Close")]

    def __init__(self, bindings: list[Binding]) -> None:
        super().__init__()
        self.help_text = self.render_help_text(bindings)

    @staticmethod
    def render_help_text(bindings: list[Binding]) -> str:
        rows = []
        for binding in bindings:
            key = getattr(binding, "key", "")
            description = getattr(binding, "description", "")
            if key and description:
                rows.append(f"{key}: {description}")
        return "\n".join(
            [
                "Stage 11 Cockpit Help",
                "",
                "Keys:",
                *rows,
                "",
                "Multi-session behavior:",
                "The work list includes panes from all local tmux sessions.",
                "Enter swaps the selected pane with the cockpit-session active slot.",
                "The active slot is never inferred from another session with matching geometry.",
            ]
        )

    def compose(self) -> ComposeResult:
        yield Static(self.help_text, id="help-modal")

    def action_dismiss_help(self) -> None:
        self.dismiss()
```

- [ ] **Step 4: Update `app.py` bindings and help action**

Add the import:

```python
from .help import HelpModal
```

Replace `BINDINGS` with:

```python
    BINDINGS = [
        Binding("up", "move_up", "↑/↓ 選擇"),
        Binding("down", "move_down", "↑/↓ 選擇"),
        Binding("enter", "swap_selected", "Enter 把選中的 pane 換到我面前"),
        Binding("c", "focus_cockpit", "c 回 cockpit"),
        Binding("question_mark", "show_help", "? 顯示說明"),
    ]
```

Add this action:

```python
    def action_show_help(self) -> None:
        self.push_screen(HelpModal(self.BINDINGS))
```

Update `on_key()` with a `?` compatibility path:

```python
        if key == "enter" or key == "\r":
            self.action_swap_selected()
        elif key == "c":
            self.action_focus_cockpit()
        elif key == "?" or key == "question_mark":
            self.action_show_help()
```

- [ ] **Step 5: Run help tests and commit**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_help_modal_lists_all_bindings tests/test_stage11_operator_cockpit.py::Stage11AppTests::test_question_mark_opens_help_modal tests/test_stage11_operator_cockpit.py::Stage11AppTests::test_help_modal_dismisses_on_escape -v
```

Expected: PASS, or SKIPPED for the two `Stage11AppTests` only when Textual is unavailable in the active environment.

Commit:

```bash
git add paulshaclaw/cockpit/app.py paulshaclaw/cockpit/help.py tests/test_stage11_operator_cockpit.py
git commit -m "feat: add cockpit hotkey help"
```

### Task 5: E2E Safety And Multi-Session Candidate Smoke

**Files:**
- Modify: `tests/test_stage11_operator_cockpit_e2e.py`

- [ ] **Step 1: Update e2e imports and add local helper**

Update imports in `tests/test_stage11_operator_cockpit_e2e.py`:

```python
from paulshaclaw.cockpit.models import PaneRecord
```

Add this helper near the top of the file:

```python
def pane_record(
    pane_id: str,
    *,
    session_name: str = "main",
    window_index: str = "0",
    title: str = "pane",
    command: str = "bash",
    left: int = 0,
    top: int = 0,
    width: int = 80,
    height: int = 24,
    active: bool = False,
    preview: tuple[str, ...] = (),
) -> PaneRecord:
    return PaneRecord(
        pane_id=pane_id,
        session_name=session_name,
        window_index=window_index,
        title=title,
        command=command,
        left=left,
        top=top,
        width=width,
        height=height,
        active=active,
        preview=preview,
    )
```

- [ ] **Step 2: Add fake multi-session candidate smoke coverage**

Add this test class before `Stage11TmuxE2ETests`:

```python
class Stage11FakeMultiSessionE2ETests(unittest.TestCase):
    def test_e2e_multi_session_pane_visible_in_candidate_list(self) -> None:
        panes = (
            pane_record("%0", session_name="main", title="cockpit", command="python", left=0, top=0, width=120, height=40),
            pane_record("%4", session_name="main", title="active", command="bash", left=120, top=0, width=120, height=40),
            pane_record("%12", session_name="work", window_index="2", title="pytest", command="python", left=0, top=0, width=100, height=30),
        )

        app = CockpitApp.from_snapshot(
            panes=panes,
            cockpit_pane_id="%0",
            cockpit_session_name="main",
            jobs_by_pane={},
            actions=LayoutActionService(),
        )

        self.assertIn("%12", [pane.pane_id for pane in app.state.candidate_section])
```

- [ ] **Step 3: Keep the real tmux e2e test isolated to its test session**

Inside `Stage11TmuxE2ETests`, add:

```python
    def _list_session_panes(
        self,
        client: TmuxClient,
        *,
        session_name: str,
        cockpit_pane_id: str,
    ):
        return tuple(
            pane
            for pane in client.list_panes(cockpit_pane_id=cockpit_pane_id)
            if pane.session_name == session_name
        )
```

Replace the client setup inside `test_app_swap_reconciles_active_slot_focuses_selected_and_returns_to_cockpit()` with:

```python
        client = TmuxClient()
        initial_panes = self._list_session_panes(
            client,
            session_name=session_name,
            cockpit_pane_id=cockpit_pane_id,
        )
        app = CockpitApp.from_snapshot(
            panes=initial_panes,
            cockpit_pane_id=cockpit_pane_id,
            cockpit_session_name=session_name,
            jobs_by_pane={},
            actions=LayoutActionService(session_target=session_name),
            pane_loader=lambda *, cockpit_pane_id: self._list_session_panes(
                client,
                session_name=session_name,
                cockpit_pane_id=cockpit_pane_id,
            ),
        )
```

- [ ] **Step 4: Run e2e tests and commit**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit_e2e.py -v
```

Expected: PASS for fake multi-session smoke; real tmux test PASS when `tmux` is installed, SKIPPED when `tmux` is unavailable.

Commit:

```bash
git add tests/test_stage11_operator_cockpit_e2e.py
git commit -m "test: cover stage11 multi-session pane listing"
```

### Task 6: Final Verification

**Files:**
- Verify: `openspec/changes/stage11-multi-session-pane-listing/`
- Verify: `docs/superpowers/plans/2026-04-28-stage11-multi-session-pane-listing.md`
- Verify: Stage 11 code and tests touched by the implementation

- [ ] **Step 1: Run the full Stage 11 test target**

Run:

```bash
.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py tests/test_stage11_operator_cockpit_e2e.py -v
```

Expected: PASS, with environment-dependent SKIPPED only for optional Textual or tmux tests.

- [ ] **Step 2: Validate OpenSpec change**

Run:

```bash
openspec validate stage11-multi-session-pane-listing --strict
```

Expected: validation succeeds for proposal, design, spec delta, and tasks.

- [ ] **Step 3: Confirm the OpenSpec apply gate is complete**

Run:

```bash
openspec status --change stage11-multi-session-pane-listing
```

Expected: `proposal`, `design`, `specs`, and `tasks` are complete, and the change is ready for implementation or archive after code lands.

- [ ] **Step 4: Check git diff scope**

Run:

```bash
git status --short
git diff --stat
```

Expected: changed paths are limited to Stage 11 cockpit files, Stage 11 tests, OpenSpec artifacts, and this plan. `scripts/start.sh` remains untouched unless it was already untracked before implementation.

- [ ] **Step 5: Final commit**

Run:

```bash
git add openspec/changes/stage11-multi-session-pane-listing docs/superpowers/plans/2026-04-28-stage11-multi-session-pane-listing.md
git commit -m "docs: propose stage11 multi-session pane listing"
```

Expected: commit succeeds after the implementation commits, or the OpenSpec/plan docs are included in the same branch history if the team prefers one proposal commit plus implementation commits.

## Self-Review Checklist

- Spec coverage:
  - All-session pane enumeration: Tasks 1 and 5.
  - Session/window labels: Tasks 1 and 3.
  - Cockpit-session active-slot scope: Task 2.
  - Cross-session swap through existing service: Tasks 2, 3, and 5.
  - Startup missing cockpit pane handling: Task 3.
  - Footer and `?` modal help: Task 4.
- Placeholder scan:
  - This plan contains no deferred implementation markers.
- Type consistency:
  - `PaneRecord.session_name`, `PaneRecord.window_index`, `CockpitState.cockpit_session_name`, and `CockpitApp.from_snapshot(..., cockpit_session_name=...)` are used consistently across tasks.

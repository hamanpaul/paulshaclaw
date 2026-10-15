"""Deterministic Docker runner; raw FAIL and expected historical RED are separate."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from paulshaclaw_deploy.plugin import CORE_API_VERSION, CORE_VERSION


def historical_matches(case: dict, report: dict) -> bool:
    if report.get('infrastructure_errors') or not report.get('report_complete'):
        return False
    transport = report.get('transport', {})
    if not transport.get('cleanup') or not transport.get('last_container_id'):
        return False
    expected = {step['id']: step for step in case['steps']}
    actual = {step['id']: step for step in report['steps']}
    if set(actual) != set(expected):
        return False
    saw_missing_git = False
    for sid, step in expected.items():
        result = actual[sid]
        if result.get('timed_out') or result.get('infrastructure_error'):
            return False
        if result.get('returncode') != step.get('expected_red_exit_code', step.get('expected_exit_code', 0)):
            return False
        marker = step.get('expected_red_stderr')
        if marker and marker not in result.get('stderr', ''):
            return False
        saw_missing_git |= bool(marker and "Cannot find command 'git'" in marker)
    return saw_missing_git


class DeployRunner:
    def __init__(self, plugin):
        self.plugin = plugin

    def run(self, orchestrator, plugin_name, case_ids=None, dut_fw_ver=None, provider_config=None):
        del orchestrator, plugin_name, dut_fw_ver, provider_config
        output = Path(os.environ.get('TESTPILOT_REPORT_DIR', 'reports/deploy'))
        return self.run_cases(case_ids, output)

    def run_cases(self, case_ids, output: Path) -> dict[str, Any]:
        cases = self.plugin.discover_cases()
        selected = set(case_ids or [case['id'] for case in cases])
        if selected - {case['id'] for case in cases}:
            raise ValueError('unknown case IDs')
        self.plugin.prepare_run(list(selected))
        rows = []
        for definition in cases:
            if definition['id'] not in selected:
                continue
            # Both Python 3.10 and 3.12 must pass the git control.
            images = definition.get('image_comparison', []) if definition['id'].startswith('tc1g-') else [{}]
            for image in images:
                case = deepcopy(definition)
                case['topology']['devices']['dut'].update(image)
                result = self.plugin.run_pipeline(case, {})
                raw = deepcopy(self.plugin.last_run_metadata.get('case_report', {}))
                if not raw:
                    raw = {'case_id': case['id'], 'steps': [], 'report_complete': False,
                           'infrastructure_errors': [{'reason': result['comment']}]}
                raw['status'] = 'PASS' if result['verdict'] else 'FAIL'
                raw['expected_red_reproduced'] = historical_matches(case, raw)
                rows.append(raw)
                print(f"{case['id']} {image.get('image', 'ubuntu:24.04')}: {raw['status']} expected_red={raw['expected_red_reproduced']}", flush=True)
        report = {
            'plugin': self.plugin.name, 'core_version': CORE_VERSION, 'core_api_version': CORE_API_VERSION,
            'generated_at': datetime.now(timezone.utc).isoformat(), 'selected_case_ids': sorted(selected),
            'cases': rows, 'status': 'failed' if any(row['status'] == 'FAIL' for row in rows) else 'passed',
        }
        output.mkdir(parents=True, exist_ok=True)
        path = output / 'deploy-report.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        lines = ['# Deploy regression report', '', '| Case | Image | Raw verdict | Expected historical RED | Cleanup |', '|---|---|---|---|---|']
        for row in rows:
            transport = row.get('transport', {})
            lines.append(f"| {row['case_id']} | {transport.get('image', '?')} | {row['status']} | {row['expected_red_reproduced']} | {transport.get('cleanup', False)} |")
            lines.extend(['', f"## {row['case_id']} ({transport.get('image', '?')})", '', '| Step | Exit | Successful install gate |', '|---|---|---|'])
            lines.extend(f"| {step['id']} | {step['returncode']} | {step['success']} |" for step in row.get('steps', []))
        lines.extend(['', '[Full stdout, stderr, provenance and cleanup evidence](deploy-report.json)', ''])
        (output / 'deploy-report.md').write_text('\n'.join(lines))
        return {**report, 'json_report_path': str(path), 'md_report_path': str(output / 'deploy-report.md')}

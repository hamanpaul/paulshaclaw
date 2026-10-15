"""Accept only the full observed historical matrix, never synthetic case output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from paulshaclaw_deploy.plugin import Plugin
from paulshaclaw_deploy.runner import historical_matches

RED = {'tc1-readme-a-venv-install', 'tc1p-readme-a-pipx-install'}


def validate_report(report: dict) -> bool:
    cases = {case['id']: case for case in Plugin().discover_cases()}
    rows = report.get('cases', [])
    required = {(cid, 'ubuntu:24.04') for cid in cases}
    required.add(('tc1g-readme-a-venv-install-with-git', 'ubuntu:22.04'))
    observed = {(row.get('case_id'), row.get('transport', {}).get('image')) for row in rows}
    if observed != required or len(rows) != len(required):
        return False
    for row in rows:
        cid = row['case_id']
        transport = row.get('transport', {})
        if row.get('infrastructure_errors') or not row.get('report_complete') or not transport.get('cleanup'):
            return False
        expected_digests = {
            'ubuntu:22.04': 'sha256:2edbbc5dc405e9612ba3584ce95480277e3eb374407b5505fe26f17df77c7dbc',
            'ubuntu:24.04': 'sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517',
        }
        if (transport.get('uid') != 1000 or not transport.get('last_container_id')
                or not transport.get('cleanup_attempted')
                or transport.get('image_digest') != expected_digests.get(transport.get('image'))):
            return False
        readme = row.get('readme', {})
        if readme.get('sha256') != 'ed87ae8fe9f64e82e478bfb490bba0f741a221b407a3819e4e9bf3b11b933979':
            return False
        artifact = row.get('artifacts', {}).get('historical', {})
        if artifact.get('sha256') != 'cc2e0771ba09030b23280ba1ab19a898ce147f8ef4e942a226bf10ddcd2be13f':
            return False
        if cid in RED:
            if row.get('status') != 'FAIL' or not historical_matches(cases[cid], row):
                return False
        else:
            captured = {step['id']: {'captured': step} for step in row.get('steps', [])}
            if row.get('status') != 'PASS' or not Plugin().evaluate(cases[cid], {'steps': captured}):
                return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    if not validate_report(report):
        raise SystemExit('FAIL: historical matrix missing, unexpected, or infrastructure failure')
    print('PASS: TC-1/TC-1p missing-git RED; TC-1c/TC-1g GREEN; all five containers cleaned')


if __name__ == '__main__':
    main()

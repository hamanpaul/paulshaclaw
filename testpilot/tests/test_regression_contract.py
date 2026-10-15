from copy import deepcopy
from pathlib import Path

from paulshaclaw_deploy.plugin import Plugin, parse_prerequisites
from test_plugin import FakeTransport


def test_historical_readme_mentions_git_without_declaring_it_as_prerequisite():
    readme = Path(__file__).parents[1] / 'paulshaclaw_deploy/fixtures/README-v0.2.7.txt'
    assert parse_prerequisites(readme.read_text())['packages'] == []


def test_only_explicit_apt_declaration_supplies_safe_package_names():
    parsed = parse_prerequisites('### A. Install\nGit dependencies need git.\n'
                                 'sudo apt install python3 python3-venv git\n'
                                 '### B. Developer\nsudo apt install pipx\n')
    assert parsed['packages'] == ['git', 'python3', 'python3-venv']


def test_venv_baseline_does_not_install_pipx():
    plugin = Plugin()
    case = plugin.discover_cases()[0]
    assert plugin._readme_metadata(case)['packages'] == ['python3', 'python3-venv']


def test_pipeline_keeps_later_diagnostics_after_an_unexpected_nonzero():
    plugin = Plugin()
    case = {'id': 'diagnostic', 'steps': [
        {'id': 'install', 'command': 'false', 'expected_exit_code': 0},
        {'id': 'version', 'command': 'version', 'expected_exit_code': 0},
    ], 'pass_criteria': []}
    transport = FakeTransport({'false': {'returncode': 1, 'stdout': '', 'stderr': 'network error', 'elapsed': 0.1}})
    result = plugin.run_pipeline(case, {'transport': transport})
    assert result['verdict'] is False
    assert [step['id'] for step in plugin.case_reports['diagnostic'][0]['steps']] == ['install', 'version']
    assert plugin.case_reports['diagnostic'][0]['transport']['cleanup'] is True


def test_expected_missing_git_step_is_still_a_failed_install():
    plugin = Plugin()
    transport = FakeTransport({'install': {'returncode': 1, 'stdout': '', 'stderr': "Cannot find command 'git'", 'elapsed': 0.1}})
    step = {'id': 'install', 'command': 'install', 'expected_exit_code': 0,
            'expected_red_exit_code': 1, 'expected_red_stderr': "Cannot find command 'git'"}
    result = plugin.execute_step({}, step, {'transport': transport})
    assert result['success'] is False
    assert result['captured']['red_oracle_matched'] is True


def test_green_version_gate_rejects_extra_output():
    plugin = Plugin()
    case = {'steps': [{'id': 'version', 'expected_exit_code': 0, 'stdout_equals': 'paulshaclaw 0.2.7'}], 'pass_criteria': []}
    result = {'captured': {'returncode': 0, 'stdout': 'debug message\npaulshaclaw 0.2.7\n', 'stderr': ''}}
    assert plugin.evaluate(case, {'steps': {'version': result}}) is False


def test_readme_code_comments_and_mentions_do_not_declare_packages():
    text = '### A. Install\n```bash\n# 1. git+SHA dependencies\npython3 -m venv env\n```\n'
    assert parse_prerequisites(text)['packages'] == []


def test_prerequisites_use_testbed_readme_and_preserve_no_deps_control(tmp_path):
    import yaml
    readme = tmp_path / 'README.md'
    readme.write_text('### A. Install\n```bash\n# 0. System\nsudo apt install python3 python3-venv git\n```\n')
    testbed = tmp_path / 'testbed.yaml'
    testbed.write_text(yaml.safe_dump({'readme': {'path': str(readme), 'revision': 'candidate'}}))
    plugin = Plugin(testbed)
    cases = {case['id']: case for case in plugin.discover_cases()}
    assert plugin._readme_metadata(cases['tc1-readme-a-venv-install'])['packages'] == ['git', 'python3', 'python3-venv']
    assert plugin._readme_metadata(cases['tc1c-entry-points-intact-no-deps'])['packages'] == ['python3', 'python3-venv']


def test_unavailable_transport_reports_infrastructure_without_unbound_diagnostic(tmp_path):
    import yaml
    path = tmp_path / 'testbed.yaml'
    path.write_text(yaml.safe_dump({'topology': {}}))
    result = Plugin(path).execute_step({}, {'id': 'probe', 'command': 'true'}, {})
    assert result['infrastructure_error'] is True
    assert result['captured']['returncode'] == -1

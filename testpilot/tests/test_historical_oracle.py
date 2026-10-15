from copy import deepcopy
import importlib.util
from pathlib import Path


def test_historical_oracle_uses_observations_and_rejects_unrelated_failure():
    script = Path(__file__).parents[1] / 'scripts/check_expected_red_oracle.py'
    spec = importlib.util.spec_from_file_location('oracle', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(getattr(module, 'validate_report', None)), 'oracle must consume real reports'
    report = {'cases': [{'case_id': 'tc1-readme-a-venv-install', 'status': 'FAIL',
        'expected_red_reproduced': True, 'report_complete': True,
        'infrastructure_errors': [{'reason': 'network'}], 'steps': []}]}
    assert module.validate_report(report) is False


def load_oracle():
    script = Path(__file__).parents[1] / 'scripts/check_expected_red_oracle.py'
    spec = importlib.util.spec_from_file_location('oracle', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_report


def observed_matrix():
    import json
    # Captured Docker matrix, with irrelevant apt/pip logs omitted.
    return json.loads((Path(__file__).parent / 'fixtures/historical-report.json').read_text())


def test_complete_observed_matrix_matches():
    assert load_oracle()(observed_matrix()) is True


def test_only_one_matching_red_step_is_not_a_reproduction():
    report = observed_matrix()
    report['cases'][0]['steps'][4]['returncode'] = 9
    assert load_oracle()(report) is False


def test_control_cleanup_requires_container_identity():
    report = observed_matrix()
    report['cases'][1]['transport']['last_container_id'] = ''
    assert load_oracle()(report) is False


def test_root_execution_is_not_a_nonroot_control():
    report = observed_matrix()
    report['cases'][1]['transport']['uid'] = 0
    assert load_oracle()(report) is False


def test_unpinned_image_is_not_the_declared_matrix():
    report = observed_matrix()
    report['cases'][1]['transport']['image_digest'] = 'sha256:' + '0' * 64
    assert load_oracle()(report) is False

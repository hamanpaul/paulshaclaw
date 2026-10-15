"""Run the published v0.2.7 artifact; artifact download is a separate explicit step."""
import argparse
from pathlib import Path
import tempfile
import yaml
from paulshaclaw_deploy.plugin import Plugin
from paulshaclaw_deploy.runner import DeployRunner
from check_expected_red_oracle import validate_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact-dir', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    template = Plugin().plugin_root / 'testbed.yaml.example'
    data = yaml.safe_load(template.read_text())
    data['artifacts']['root'] = str(args.artifact_dir.resolve())
    with tempfile.TemporaryDirectory(prefix='psc-deploy-testbed-') as directory:
        path = Path(directory) / 'testbed.yaml'
        path.write_text(yaml.safe_dump(data))
        report = DeployRunner(Plugin(path)).run_cases(None, args.report_dir)
    if not validate_report(report):
        raise SystemExit('FAIL: historical matrix missing, unexpected, or infrastructure failure')
    print('PASS: historical RED and GREEN controls verified; raw report retains FAIL')


if __name__ == '__main__':
    main()

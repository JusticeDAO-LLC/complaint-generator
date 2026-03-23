import importlib.util
from pathlib import Path


def _load_cli_module():
    module_path = Path(__file__).resolve().parents[1] / 'scripts' / 'run_claim_support_review_regression.py'
    spec = importlib.util.spec_from_file_location('run_claim_support_review_regression', module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_parser_supports_browser_mode_and_list():
    cli = _load_cli_module()
    parser = cli.create_parser()

    args = parser.parse_args(['--browser', 'on', '--list'])

    assert args.browser == 'on'
    assert args.list is True


def test_resolve_test_targets_auto_includes_browser_when_available():
    cli = _load_cli_module()

    targets = cli.resolve_test_targets('auto', browser_available=True)

    assert targets[:len(cli.BASE_TESTS)] == cli.BASE_TESTS
    assert targets[len(cli.BASE_TESTS):] == cli.BROWSER_TESTS


def test_resolve_test_targets_auto_omits_browser_when_unavailable():
    cli = _load_cli_module()

    targets = cli.resolve_test_targets('auto', browser_available=False)

    assert targets == cli.BASE_TESTS


def test_build_pytest_command_places_passthrough_args_before_targets():
    cli = _load_cli_module()

    command = cli.build_pytest_command(
        browser_mode='off',
        browser_available=False,
        pytest_args=['-k', 'claim_support'],
        python_executable='.venv/bin/python',
    )

    assert command[:6] == [
        '.venv/bin/python',
        '-m',
        'pytest',
        '-q',
        '-k',
        'claim_support',
    ]
    assert command[6:] == cli.BASE_TESTS


def test_resolve_test_targets_on_includes_all_browser_suites():
    cli = _load_cli_module()

    targets = cli.resolve_test_targets('on', browser_available=False)

    assert targets[:len(cli.BASE_TESTS)] == cli.BASE_TESTS
    assert targets[len(cli.BASE_TESTS):] == cli.BROWSER_TESTS
    assert 'tests/test_complaint_generator_package.py' in targets
    assert 'tests/test_complaint_generator_site_playwright.py' in targets
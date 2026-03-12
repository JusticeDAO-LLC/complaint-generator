from unittest.mock import Mock

from applications.cli import CLI


def _make_cli(mediator=None):
    cli = CLI.__new__(CLI)
    cli.mediator = mediator or Mock()
    cli.print_response = Mock()
    cli.print_error = Mock()
    cli.print_commands = Mock()
    cli.feed = Mock()
    cli.save = Mock()
    cli.resume = Mock()
    return cli


def test_parse_command_options_supports_key_value_and_bools():
    cli = _make_cli()

    positionals, options = cli._parse_command_options([
        'employment retaliation',
        'include_follow_up_plan=false',
        'follow_up_max_tasks_per_claim=2',
        'follow_up_force=true',
    ])

    assert positionals == ['employment retaliation']
    assert options['include_follow_up_plan'] is False
    assert options['follow_up_max_tasks_per_claim'] == 2
    assert options['follow_up_force'] is True


def test_parse_command_options_splits_required_support_kinds():
    cli = _make_cli()

    positionals, options = cli._parse_command_options([
        'required_support_kinds=evidence,authority,expert',
    ])

    assert positionals == []
    assert options['required_support_kinds'] == ['evidence', 'authority', 'expert']


def test_claim_review_command_calls_mediator_builder():
    mediator = Mock()
    mediator.build_claim_support_review_payload.return_value = {'ok': True}
    cli = _make_cli(mediator)

    cli.claim_review([
        'claim_type=employment retaliation',
        'required_support_kinds=evidence,authority',
        'include_follow_up_plan=false',
        'follow_up_max_tasks_per_claim=1',
    ])

    mediator.build_claim_support_review_payload.assert_called_once_with(
        claim_type='employment retaliation',
        user_id=None,
        required_support_kinds=['evidence', 'authority'],
        follow_up_cooldown_seconds=3600,
        include_support_summary=True,
        include_overview=True,
        include_follow_up_plan=False,
        execute_follow_up=False,
        follow_up_support_kind=None,
        follow_up_max_tasks_per_claim=1,
    )
    cli.print_response.assert_called_once()


def test_claim_review_command_prints_parse_quality_summary_before_json():
    mediator = Mock()
    mediator.build_claim_support_review_payload.return_value = {
        'claim_coverage_summary': {
            'retaliation': {
                'low_quality_parsed_record_count': 2,
                'parse_quality_issue_element_count': 1,
                'avg_parse_quality_score': 62.5,
                'parse_quality_issue_elements': ['Causal connection'],
                'parse_quality_recommendation': 'improve_parse_quality',
            }
        }
    }
    cli = _make_cli(mediator)

    cli.claim_review(['claim_type=retaliation'])

    rendered = cli.print_response.call_args[0][0]
    assert 'claim review parse-quality summary:' in rendered
    assert '- retaliation: low_quality=2 issue_elements=1 avg_quality=62.50' in rendered
    assert 'refresh: Causal connection' in rendered
    assert 'recommendation: improve_parse_quality' in rendered
    assert '"claim_coverage_summary"' in rendered


def test_execute_follow_up_command_calls_mediator_builder():
    mediator = Mock()
    mediator.build_claim_support_follow_up_execution_payload.return_value = {'executed': True}
    cli = _make_cli(mediator)

    cli.execute_follow_up([
        'civil rights',
        'required_support_kinds=evidence,authority',
        'follow_up_support_kind=authority',
        'follow_up_max_tasks_per_claim=2',
        'follow_up_force=true',
        'include_post_execution_review=false',
    ])

    mediator.build_claim_support_follow_up_execution_payload.assert_called_once_with(
        claim_type='civil rights',
        user_id=None,
        required_support_kinds=['evidence', 'authority'],
        follow_up_cooldown_seconds=3600,
        follow_up_support_kind='authority',
        follow_up_max_tasks_per_claim=2,
        follow_up_force=True,
        include_post_execution_review=False,
        include_support_summary=True,
        include_overview=True,
        include_follow_up_plan=True,
    )
    cli.print_response.assert_called_once()


def test_execute_follow_up_command_prints_execution_quality_summary_before_json():
    mediator = Mock()
    mediator.build_claim_support_follow_up_execution_payload.return_value = {
        'follow_up_execution': {'retaliation': {'task_count': 1}},
        'execution_quality_summary': {
            'retaliation': {
                'quality_improvement_status': 'improved',
                'pre_low_quality_parsed_record_count': 1,
                'post_low_quality_parsed_record_count': 0,
                'parse_quality_task_count': 1,
                'resolved_parse_quality_issue_elements': ['Causal connection'],
                'remaining_parse_quality_issue_elements': [],
            }
        },
    }
    cli = _make_cli(mediator)

    cli.execute_follow_up(['claim_type=retaliation'])

    rendered = cli.print_response.call_args[0][0]
    assert 'follow-up execution quality summary:' in rendered
    assert '- retaliation: status=improved low_quality=1->0 parse_tasks=1' in rendered
    assert 'resolved: Causal connection' in rendered
    assert '"execution_quality_summary"' in rendered


def test_execute_follow_up_command_prints_recommendation_when_parse_quality_still_needed():
    mediator = Mock()
    mediator.build_claim_support_follow_up_execution_payload.return_value = {
        'follow_up_execution': {'retaliation': {'task_count': 1}},
        'execution_quality_summary': {
            'retaliation': {
                'quality_improvement_status': 'unchanged',
                'pre_low_quality_parsed_record_count': 1,
                'post_low_quality_parsed_record_count': 1,
                'parse_quality_task_count': 1,
                'resolved_parse_quality_issue_elements': [],
                'remaining_parse_quality_issue_elements': ['Causal connection'],
                'recommended_next_action': 'improve_parse_quality',
            }
        },
    }
    cli = _make_cli(mediator)

    cli.execute_follow_up(['claim_type=retaliation'])

    rendered = cli.print_response.call_args[0][0]
    assert 'recommendation: improve_parse_quality still needed' in rendered


def test_interpret_command_routes_new_commands():
    cli = _make_cli()
    cli.claim_review = Mock()
    cli.execute_follow_up = Mock()

    cli.interpret_command('claim-review claim_type=retaliation')
    cli.interpret_command('execute-follow-up claim_type=retaliation follow_up_force=true')

    cli.claim_review.assert_called_once_with(['claim_type=retaliation'])
    cli.execute_follow_up.assert_called_once_with([
        'claim_type=retaliation',
        'follow_up_force=true',
    ])
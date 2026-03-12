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


def test_parse_command_options_splits_export_lists():
    cli = _make_cli()

    positionals, options = cli._parse_command_options([
        'output_formats=docx,pdf,txt',
        'plaintiff_names=Jane Doe,John Doe',
        'defendant_names=Acme Corp',
        'requested_relief=Back pay,Injunctive relief',
    ])

    assert positionals == []
    assert options['output_formats'] == ['docx', 'pdf', 'txt']
    assert options['plaintiff_names'] == ['Jane Doe', 'John Doe']
    assert options['defendant_names'] == ['Acme Corp']
    assert options['requested_relief'] == ['Back pay', 'Injunctive relief']


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
                'authority_treatment_summary': {
                    'supportive_authority_link_count': 1,
                    'adverse_authority_link_count': 1,
                    'uncertain_authority_link_count': 1,
                    'treatment_type_counts': {'questioned': 1, 'limits': 1},
                },
            }
        },
        'follow_up_plan_summary': {
            'retaliation': {
                'authority_search_program_task_count': 1,
                'authority_search_program_count': 2,
                'authority_search_program_type_counts': {
                    'fact_pattern_search': 1,
                    'treatment_check_search': 1,
                },
                'authority_search_intent_counts': {
                    'confirm_good_law': 1,
                    'support': 1,
                },
                'primary_authority_program_type_counts': {
                    'fact_pattern_search': 1,
                },
                'primary_authority_program_bias_counts': {
                    'uncertain': 1,
                },
                'primary_authority_program_rule_bias_counts': {
                    'exception': 1,
                },
            }
        }
    }
    cli = _make_cli(mediator)

    cli.claim_review(['claim_type=retaliation'])

    rendered = cli.print_response.call_args[0][0]
    assert 'claim review quality summary:' in rendered
    assert '- retaliation: low_quality=2 issue_elements=1 avg_quality=62.50 authority_supportive=1 authority_adverse=1 authority_uncertain=1' in rendered
    assert 'refresh: Causal connection' in rendered
    assert 'authority_treatments: limits=1, questioned=1' in rendered
    assert 'recommendation: improve_parse_quality' in rendered
    assert 'follow-up plan authority search summary:' in rendered
    assert '- retaliation: authority_program_tasks=1 authority_programs=2' in rendered
    assert 'program_types: fact_pattern_search=1, treatment_check_search=1' in rendered
    assert 'search_intents: confirm_good_law=1, support=1' in rendered
    assert 'primary_programs: fact_pattern_search=1' in rendered
    assert 'primary_biases: uncertain=1' in rendered
    assert 'primary_rule_biases: exception=1' in rendered
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
        'follow_up_execution_summary': {
            'retaliation': {
                'authority_search_program_task_count': 1,
                'authority_search_program_count': 2,
                'authority_search_program_type_counts': {
                    'adverse_authority_search': 1,
                    'treatment_check_search': 1,
                },
                'authority_search_intent_counts': {
                    'confirm_good_law': 1,
                    'oppose': 1,
                },
                'primary_authority_program_type_counts': {
                    'adverse_authority_search': 1,
                },
                'primary_authority_program_bias_counts': {
                    'adverse': 1,
                },
                'primary_authority_program_rule_bias_counts': {
                    'procedural_prerequisite': 1,
                },
            }
        },
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
    assert 'follow-up execution authority search summary:' in rendered
    assert '- retaliation: authority_program_tasks=1 authority_programs=2' in rendered
    assert 'program_types: adverse_authority_search=1, treatment_check_search=1' in rendered
    assert 'search_intents: confirm_good_law=1, oppose=1' in rendered
    assert 'primary_programs: adverse_authority_search=1' in rendered
    assert 'primary_biases: adverse=1' in rendered
    assert 'primary_rule_biases: procedural_prerequisite=1' in rendered
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


def test_export_complaint_command_calls_document_package_builder():
    mediator = Mock()
    mediator.build_formal_complaint_document_package.return_value = {
        'draft': {'title': 'Jane Doe v. Acme Corporation'},
        'artifacts': {'docx': {'path': '/tmp/test.docx'}},
    }
    cli = _make_cli(mediator)

    cli.export_complaint([
        '/tmp/out',
        'district=District of Columbia',
        'case_number=25-cv-00001',
        'plaintiff_names=Jane Doe',
        'defendant_names=Acme Corporation',
        'output_formats=docx,pdf',
    ])

    mediator.build_formal_complaint_document_package.assert_called_once_with(
        user_id=None,
        court_name='United States District Court',
        district='District of Columbia',
        division=None,
        court_header_override=None,
        case_number='25-cv-00001',
        title_override=None,
        plaintiff_names=['Jane Doe'],
        defendant_names=['Acme Corporation'],
        requested_relief=None,
        output_dir='/tmp/out',
        output_formats=['docx', 'pdf'],
    )
    cli.print_response.assert_called_once()


def test_export_complaint_command_prints_summary_before_json():
    mediator = Mock()
    mediator.build_formal_complaint_document_package.return_value = {
        'draft': {
            'title': 'Jane Doe v. Acme Corporation',
            'court_header': 'IN THE UNITED STATES DISTRICT COURT FOR THE DISTRICT OF COLUMBIA',
            'case_caption': {'case_number': '25-cv-00001'},
            'claims_for_relief': [{}, {}],
            'exhibits': [{}, {}],
        },
        'artifacts': {
            'docx': {'path': '/tmp/test.docx'},
            'pdf': {'path': '/tmp/test.pdf'},
        },
    }
    cli = _make_cli(mediator)

    cli.export_complaint(['district=District of Columbia'])

    rendered = cli.print_response.call_args[0][0]
    assert 'formal complaint export:' in rendered
    assert 'title: Jane Doe v. Acme Corporation' in rendered
    assert 'court: IN THE UNITED STATES DISTRICT COURT FOR THE DISTRICT OF COLUMBIA' in rendered
    assert 'case_number: 25-cv-00001' in rendered
    assert 'claims: 2' in rendered
    assert 'exhibits: 2' in rendered
    assert '- docx: /tmp/test.docx' in rendered
    assert '- pdf: /tmp/test.pdf' in rendered
    assert '"artifacts"' in rendered


def test_interpret_command_routes_new_commands():
    cli = _make_cli()
    cli.claim_review = Mock()
    cli.execute_follow_up = Mock()
    cli.export_complaint = Mock()

    cli.interpret_command('claim-review claim_type=retaliation')
    cli.interpret_command('execute-follow-up claim_type=retaliation follow_up_force=true')
    cli.interpret_command('export-complaint /tmp/out district="District of Columbia"')

    cli.claim_review.assert_called_once_with(['claim_type=retaliation'])
    cli.execute_follow_up.assert_called_once_with([
        'claim_type=retaliation',
        'follow_up_force=true',
    ])
    cli.export_complaint.assert_called_once_with([
        '/tmp/out',
        'district=District of Columbia',
    ])
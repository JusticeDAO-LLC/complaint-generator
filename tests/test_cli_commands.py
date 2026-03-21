from unittest.mock import Mock

import json

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
    assert options.get('include_json') is None
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
        'service_recipients=Registered Agent,Defense Counsel',
    ])

    assert positionals == []
    assert options['output_formats'] == ['docx', 'pdf', 'txt']
    assert options['plaintiff_names'] == ['Jane Doe', 'John Doe']
    assert options['defendant_names'] == ['Acme Corp']
    assert options['requested_relief'] == ['Back pay', 'Injunctive relief']
    assert options['service_recipients'] == ['Registered Agent', 'Defense Counsel']


def test_print_commands_mentions_include_json_override(capsys):
    cli = _make_cli()

    CLI.print_commands(cli)

    captured = capsys.readouterr().out
    assert '!claim-review [claim_type] [key=value]' in captured
    assert '!execute-follow-up [claim_type] [key=value]' in captured
    assert 'include_json=true for raw payload' in captured


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
        'intake_status': {
            'current_phase': 'evidence',
            'ready_to_advance': False,
            'score': 0.67,
            'remaining_gap_count': 1,
            'contradiction_count': 0,
            'next_action': {
                'action': 'validate_promoted_support',
                'validation_target_count': 2,
            },
            'primary_validation_target': {
                'claim_type': 'retaliation',
                'claim_element_id': 'adverse_action',
                'promotion_kind': 'document',
                'promotion_ref': 'doc:retaliation:1',
            },
            'document_workflow_execution_summary': {
                'iteration_count': 2,
                'accepted_iteration_count': 1,
                'first_focus_section': 'claims_for_relief',
                'first_targeted_claim_element': 'causation',
                'first_preferred_support_kind': 'testimony',
            },
            'document_execution_drift_summary': {
                'drift_flag': True,
                'top_targeted_claim_element': 'protected_activity',
                'first_executed_claim_element': 'causation',
            },
            'document_grounding_improvement_summary': {
                'initial_fact_backed_ratio': 0.2,
                'final_fact_backed_ratio': 0.45,
                'fact_backed_ratio_delta': 0.25,
                'improved_flag': True,
                'targeted_claim_elements': ['protected_activity'],
            },
        },
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
        'follow_up_history_summary': {
            'retaliation': {
                'temporal_gap_task_count': 1,
                'temporal_gap_targeted_task_count': 1,
                'temporal_rule_status_counts': {
                    'partial': 1,
                },
                'temporal_rule_blocking_reason_counts': {
                    'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.': 1,
                },
                'temporal_resolution_status_counts': {
                    'awaiting_testimony': 1,
                },
                'selected_authority_program_type_counts': {
                    'adverse_authority_search': 1,
                },
                'selected_authority_program_bias_counts': {
                    'adverse': 1,
                },
                'selected_authority_program_rule_bias_counts': {
                    'exception': 1,
                },
                'source_family_counts': {
                    'legal_authority': 1,
                },
                'artifact_family_counts': {
                    'legal_authority_reference': 1,
                },
                'content_origin_counts': {
                    'authority_reference_fallback': 1,
                },
                'primary_missing_fact_counts': {
                    'Manager knowledge': 1,
                },
                'missing_fact_bundle_counts': {
                    'Event sequence': 1,
                    'Manager knowledge': 1,
                },
                'satisfied_fact_bundle_counts': {
                    'Protected activity': 1,
                },
            }
        },
        'follow_up_history': {
            'retaliation': [
                {
                    'claim_element_text': 'Causal connection',
                    'primary_missing_fact': 'Manager knowledge',
                    'missing_fact_bundle': ['Manager knowledge', 'Event sequence'],
                    'satisfied_fact_bundle': ['Protected activity'],
                }
            ]
        },
        'follow_up_plan': {
            'retaliation': {
                'tasks': [
                    {
                        'claim_element': 'Causal connection',
                        'primary_missing_fact': 'Manager knowledge',
                        'missing_fact_bundle': ['Manager knowledge', 'Event sequence'],
                        'satisfied_fact_bundle': ['Protected activity'],
                    }
                ]
            }
        },
        'follow_up_plan_summary': {
            'retaliation': {
                'temporal_gap_task_count': 1,
                'temporal_gap_targeted_task_count': 1,
                'temporal_rule_status_counts': {
                    'partial': 1,
                },
                'temporal_rule_blocking_reason_counts': {
                    'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.': 1,
                },
                'temporal_resolution_status_counts': {
                    'awaiting_testimony': 1,
                },
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
                'support_by_kind': {
                    'authority': 1,
                },
                'source_family_counts': {
                    'legal_authority': 1,
                },
                'artifact_family_counts': {
                    'legal_authority_reference': 1,
                },
                'primary_missing_fact_counts': {
                    'Manager knowledge': 1,
                },
                'missing_fact_bundle_counts': {
                    'Event sequence': 1,
                    'Manager knowledge': 1,
                },
                'satisfied_fact_bundle_counts': {
                    'Protected activity': 1,
                },
            }
        }
    }
    cli = _make_cli(mediator)

    cli.claim_review(['claim_type=retaliation'])

    rendered = cli.print_response.call_args[0][0]
    assert 'intake status summary:' in rendered
    assert '- phase=evidence ready=false score=0.67 gaps=1 contradictions=0' in rendered
    assert 'next_action: validate_promoted_support targets=2' in rendered
    assert 'primary_validation_target: Retaliation / Adverse Action [Document] ref=doc:retaliation:1' in rendered
    assert 'document_execution: iterations=2 accepted=1 first=Claims For Relief / Causation [Testimony]' in rendered
    assert 'drafting_priority: realign to Protected Activity before further revisions (executed Causation first)' in rendered
    assert 'grounding_recovery: improved delta=+0.25 from=0.20 to=0.45 target=Protected Activity' in rendered
    assert 'claim review quality summary:' in rendered
    assert '- retaliation: low_quality=2 issue_elements=1 avg_quality=62.50 authority_supportive=1 authority_adverse=1 authority_uncertain=1' in rendered
    assert 'refresh: Causal connection' in rendered
    assert 'authority_treatments: Limits=1, Questioned=1' in rendered
    assert 'recommendation: improve_parse_quality' in rendered
    assert 'follow-up plan fact targeting:' in rendered
    assert '- retaliation:' in rendered
    assert 'Causal Connection | primary_gap=Manager knowledge | missing=Manager knowledge, Event sequence | covered=Protected activity' in rendered
    assert 'follow-up plan authority search summary:' in rendered
    assert '- retaliation: authority_program_tasks=1 authority_programs=2' in rendered
    assert 'program_types: Fact Pattern Search=1, Treatment Check Search=1' in rendered
    assert 'search_intents: Confirm Good Law=1, Support=1' in rendered
    assert 'primary_programs: Fact Pattern Search=1' in rendered
    assert 'primary_biases: Uncertain=1' in rendered
    assert 'primary_rule_biases: Exception=1' in rendered
    assert 'source_context: lane Authority=1; family Legal Authority=1; artifact Legal Authority Reference=1' in rendered
    assert 'follow-up plan chronology summary:' in rendered
    assert '- retaliation: chronology_tasks=1 chronology_targeted=1' in rendered
    assert 'rule_status: Partial=1' in rendered
    assert 'blockers: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.=1' in rendered
    assert 'handoffs: Awaiting Testimony=1' in rendered
    assert 'follow-up plan fact-target summary:' in rendered
    assert 'primary_gaps: Manager Knowledge=1' in rendered
    assert 'missing_bundle: Event Sequence=1, Manager Knowledge=1' in rendered
    assert 'covered_bundle: Protected Activity=1' in rendered
    assert 'follow-up history fact targeting:' in rendered
    assert 'follow-up history authority search summary:' in rendered
    assert '- retaliation: history_program_entries=1' in rendered
    assert 'selected_programs: Adverse Authority Search=1' in rendered
    assert 'selected_biases: Adverse=1' in rendered
    assert 'selected_rule_biases: Exception=1' in rendered
    assert 'source_context: family Legal Authority=1; artifact Legal Authority Reference=1' in rendered
    assert 'follow-up history chronology summary:' in rendered
    assert '- retaliation: chronology_tasks=1 chronology_targeted=1' in rendered
    assert 'rule_status: Partial=1' in rendered
    assert 'blockers: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.=1' in rendered
    assert 'handoffs: Awaiting Testimony=1' in rendered
    assert 'follow-up history fact-target summary:' in rendered
    assert '"claim_coverage_summary"' not in rendered


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
        'intake_status': {
            'current_phase': 'evidence',
            'ready_to_advance': False,
            'score': 0.58,
            'remaining_gap_count': 0,
            'contradiction_count': 1,
            'next_action': {
                'action': 'validate_promoted_support',
                'validation_target_count': 1,
            },
            'primary_validation_target': {
                'claim_type': 'retaliation',
                'claim_element_id': 'causation',
                'promotion_kind': 'testimony',
                'promotion_ref': 'testimony:retaliation:1',
            },
        },
        'follow_up_execution': {'retaliation': {'task_count': 1}},
        'follow_up_execution': {
            'retaliation': {
                'task_count': 1,
                'tasks': [
                    {
                        'claim_element': 'Causal connection',
                        'primary_missing_fact': 'Manager knowledge',
                        'missing_fact_bundle': ['Manager knowledge', 'Event sequence'],
                        'satisfied_fact_bundle': ['Protected activity'],
                    }
                ],
            }
        },
        'follow_up_execution_summary': {
            'retaliation': {
                    'temporal_gap_task_count': 1,
                    'temporal_gap_targeted_task_count': 1,
                    'temporal_rule_status_counts': {
                        'partial': 1,
                    },
                    'temporal_rule_blocking_reason_counts': {
                        'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.': 1,
                    },
                    'temporal_resolution_status_counts': {
                        'awaiting_testimony': 1,
                    },
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
                'support_by_kind': {
                    'authority': 1,
                },
                'source_family_counts': {
                    'legal_authority': 1,
                },
                'artifact_family_counts': {
                    'legal_authority_reference': 1,
                },
                'primary_missing_fact_counts': {
                    'Manager knowledge': 1,
                },
                'missing_fact_bundle_counts': {
                    'Event sequence': 1,
                    'Manager knowledge': 1,
                },
                'satisfied_fact_bundle_counts': {
                    'Protected activity': 1,
                },
            }
        },
        'post_execution_review': {
            'follow_up_history': {
                'retaliation': [
                    {
                        'claim_element_text': 'Causal connection',
                        'primary_missing_fact': 'Manager knowledge',
                        'missing_fact_bundle': ['Manager knowledge', 'Event sequence'],
                        'satisfied_fact_bundle': ['Protected activity'],
                    }
                ]
            },
            'follow_up_history_summary': {
                'retaliation': {
                    'temporal_gap_task_count': 1,
                    'temporal_gap_targeted_task_count': 1,
                    'temporal_rule_status_counts': {
                        'partial': 1,
                    },
                    'temporal_rule_blocking_reason_counts': {
                        'Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.': 1,
                    },
                    'temporal_resolution_status_counts': {
                        'awaiting_testimony': 1,
                    },
                    'selected_authority_program_type_counts': {
                        'element_definition_search': 1,
                    },
                    'selected_authority_program_bias_counts': {
                        'uncertain': 1,
                    },
                    'selected_authority_program_rule_bias_counts': {
                        'procedural_prerequisite': 1,
                    },
                    'source_family_counts': {
                        'legal_authority': 1,
                    },
                    'artifact_family_counts': {
                        'legal_authority_reference': 1,
                    },
                    'content_origin_counts': {
                        'authority_reference_fallback': 1,
                    },
                    'primary_missing_fact_counts': {
                        'Manager knowledge': 1,
                    },
                    'missing_fact_bundle_counts': {
                        'Event sequence': 1,
                        'Manager knowledge': 1,
                    },
                    'satisfied_fact_bundle_counts': {
                        'Protected activity': 1,
                    },
                }
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
    assert 'intake status summary:' in rendered
    assert '- phase=evidence ready=false score=0.58 gaps=0 contradictions=1' in rendered
    assert 'next_action: validate_promoted_support targets=1' in rendered
    assert 'primary_validation_target: Retaliation / Causation [Testimony] ref=testimony:retaliation:1' in rendered
    assert 'follow-up execution quality summary:' in rendered
    assert '- retaliation: status=improved low_quality=1->0 parse_tasks=1' in rendered
    assert 'resolved: Causal connection' in rendered
    assert 'follow-up execution fact targeting:' in rendered
    assert 'Causal Connection | primary_gap=Manager knowledge | missing=Manager knowledge, Event sequence | covered=Protected activity' in rendered
    assert 'follow-up execution authority search summary:' in rendered
    assert '- retaliation: authority_program_tasks=1 authority_programs=2' in rendered
    assert 'program_types: Adverse Authority Search=1, Treatment Check Search=1' in rendered
    assert 'search_intents: Confirm Good Law=1, Oppose=1' in rendered
    assert 'primary_programs: Adverse Authority Search=1' in rendered
    assert 'primary_biases: Adverse=1' in rendered
    assert 'primary_rule_biases: Procedural Prerequisite=1' in rendered
    assert 'source_context: lane Authority=1; family Legal Authority=1; artifact Legal Authority Reference=1' in rendered
    assert 'follow-up execution chronology summary:' in rendered
    assert '- retaliation: chronology_tasks=1 chronology_targeted=1' in rendered
    assert 'rule_status: Partial=1' in rendered
    assert 'blockers: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.=1' in rendered
    assert 'handoffs: Awaiting Testimony=1' in rendered
    assert 'follow-up execution fact-target summary:' in rendered
    assert 'primary_gaps: Manager Knowledge=1' in rendered
    assert 'missing_bundle: Event Sequence=1, Manager Knowledge=1' in rendered
    assert 'covered_bundle: Protected Activity=1' in rendered
    assert 'follow-up history fact targeting:' in rendered
    assert 'follow-up history authority search summary:' in rendered
    assert '- retaliation: history_program_entries=1' in rendered
    assert 'selected_programs: Element Definition Search=1' in rendered
    assert 'selected_biases: Uncertain=1' in rendered
    assert 'selected_rule_biases: Procedural Prerequisite=1' in rendered
    assert 'source_context: family Legal Authority=1; artifact Legal Authority Reference=1' in rendered
    assert 'follow-up history chronology summary:' in rendered
    assert '- retaliation: chronology_tasks=1 chronology_targeted=1' in rendered
    assert 'rule_status: Partial=1' in rendered
    assert 'blockers: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.=1' in rendered
    assert 'handoffs: Awaiting Testimony=1' in rendered
    assert 'follow-up history fact-target summary:' in rendered
    assert '"execution_quality_summary"' not in rendered


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
                'primary_validation_target': {
                    'claim_type': 'retaliation',
                    'claim_element_id': 'adverse_action',
                    'promotion_kind': 'document',
                    'promotion_ref': 'doc:retaliation:1',
                },
            }
        },
    }
    cli = _make_cli(mediator)

    cli.execute_follow_up(['claim_type=retaliation'])

    rendered = cli.print_response.call_args[0][0]
    assert 'recommendation: improve_parse_quality still needed' in rendered
    assert 'validation target: Retaliation / Adverse Action [Document] ref=doc:retaliation:1' in rendered


def test_claim_review_command_can_suppress_raw_json():
    mediator = Mock()
    mediator.build_claim_support_review_payload.return_value = {
        'intake_status': {
            'current_phase': 'evidence',
            'ready_to_advance': False,
            'score': 0.5,
            'remaining_gap_count': 1,
            'contradiction_count': 0,
        },
        'claim_coverage_summary': {
            'retaliation': {
                'low_quality_parsed_record_count': 0,
                'parse_quality_issue_element_count': 0,
                'avg_parse_quality_score': 100.0,
                'authority_treatment_summary': {},
            }
        },
    }
    cli = _make_cli(mediator)

    cli.claim_review(['claim_type=retaliation', 'include_json=false'])

    rendered = cli.print_response.call_args[0][0]
    assert 'intake status summary:' in rendered
    assert 'claim review quality summary:' in rendered
    assert '"claim_coverage_summary"' not in rendered


def test_execute_follow_up_command_can_suppress_raw_json():
    mediator = Mock()
    mediator.build_claim_support_follow_up_execution_payload.return_value = {
        'intake_status': {
            'current_phase': 'evidence',
            'ready_to_advance': False,
            'score': 0.5,
            'remaining_gap_count': 0,
            'contradiction_count': 1,
        },
        'execution_quality_summary': {
            'retaliation': {
                'quality_improvement_status': 'unchanged',
                'pre_low_quality_parsed_record_count': 1,
                'post_low_quality_parsed_record_count': 1,
                'parse_quality_task_count': 1,
                'resolved_parse_quality_issue_elements': [],
                'remaining_parse_quality_issue_elements': ['Causal connection'],
            }
        },
    }
    cli = _make_cli(mediator)

    cli.execute_follow_up(['claim_type=retaliation', 'include_json=false'])

    rendered = cli.print_response.call_args[0][0]
    assert 'intake status summary:' in rendered
    assert 'follow-up execution quality summary:' in rendered
    assert '"execution_quality_summary"' not in rendered


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
        'county=Washington County',
        'case_number=25-cv-00001',
        'lead_case_number=24-cv-00077',
        'related_case_number=24-cv-00110',
        'assigned_judge=Hon. Maria Valdez',
        'courtroom=Courtroom 4A',
        'plaintiff_names=Jane Doe',
        'defendant_names=Acme Corporation',
        'jury_demand=true',
        'jury_demand_text=Plaintiff demands a trial by jury on all issues so triable.',
        'signer_name=Jane Doe',
        'signer_title=Counsel for Plaintiff',
        'signer_firm=Doe Legal Advocacy PLLC',
        'signer_bar_number=DC-10101',
        'signer_contact=123 Main Street',
        'additional_signers=[{"name":"John Roe, Esq.","title":"Co-Counsel for Plaintiff","firm":"Roe Civil Rights Group","bar_number":"DC-20202","contact":"456 Side Street"}]',
        'declarant_name=Jane Doe',
        'affidavit_title=AFFIDAVIT OF JANE DOE REGARDING RETALIATION',
        "affidavit_intro=I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
        'affidavit_facts=["I reported discrimination to human resources on March 3, 2026.", "Defendant terminated my employment two days later."]',
        'affidavit_supporting_exhibits=[{"label":"Affidavit Ex. 1","title":"HR Complaint Email","link":"https://example.org/hr-email.pdf","summary":"Email reporting discrimination to HR."}]',
        'affidavit_include_complaint_exhibits=false',
        'affidavit_venue_lines=["State of California", "County of San Francisco"]',
        'affidavit_jurat=Subscribed and sworn to before me on March 13, 2026 by Jane Doe.',
        'affidavit_notary_block=["__________________________________", "Notary Public for the State of California", "My commission expires: March 13, 2029"]',
        'service_method=CM/ECF',
        'service_recipients=Registered Agent for Acme Corporation,Defense Counsel',
        'service_recipient_details=[{"recipient":"Defense Counsel","method":"Email","address":"counsel@example.com"}]',
        'signature_date=2026-03-12',
        'verification_date=2026-03-12',
        'service_date=2026-03-13',
        'output_formats=docx,pdf',
    ])

    mediator.build_formal_complaint_document_package.assert_called_once_with(
        user_id=None,
        court_name='United States District Court',
        district='District of Columbia',
        county='Washington County',
        division=None,
        court_header_override=None,
        case_number='25-cv-00001',
        lead_case_number='24-cv-00077',
        related_case_number='24-cv-00110',
        assigned_judge='Hon. Maria Valdez',
        courtroom='Courtroom 4A',
        title_override=None,
        plaintiff_names=['Jane Doe'],
        defendant_names=['Acme Corporation'],
        requested_relief=None,
        jury_demand=True,
        jury_demand_text='Plaintiff demands a trial by jury on all issues so triable.',
        signer_name='Jane Doe',
        signer_title='Counsel for Plaintiff',
        signer_firm='Doe Legal Advocacy PLLC',
        signer_bar_number='DC-10101',
        signer_contact='123 Main Street',
        additional_signers=[{'name': 'John Roe, Esq.', 'title': 'Co-Counsel for Plaintiff', 'firm': 'Roe Civil Rights Group', 'bar_number': 'DC-20202', 'contact': '456 Side Street'}],
        declarant_name='Jane Doe',
        affidavit_title='AFFIDAVIT OF JANE DOE REGARDING RETALIATION',
        affidavit_intro="I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
        affidavit_facts=['I reported discrimination to human resources on March 3, 2026.', 'Defendant terminated my employment two days later.'],
        affidavit_supporting_exhibits=[{'label': 'Affidavit Ex. 1', 'title': 'HR Complaint Email', 'link': 'https://example.org/hr-email.pdf', 'summary': 'Email reporting discrimination to HR.'}],
        affidavit_include_complaint_exhibits=False,
        affidavit_venue_lines=['State of California', 'County of San Francisco'],
        affidavit_jurat='Subscribed and sworn to before me on March 13, 2026 by Jane Doe.',
        affidavit_notary_block=['__________________________________', 'Notary Public for the State of California', 'My commission expires: March 13, 2029'],
        service_method='CM/ECF',
        service_recipients=['Registered Agent for Acme Corporation', 'Defense Counsel'],
        service_recipient_details=[{'recipient': 'Defense Counsel', 'method': 'Email', 'address': 'counsel@example.com'}],
        signature_date='2026-03-12',
        verification_date='2026-03-12',
        service_date='2026-03-13',
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
    cli.adversarial_autopatch = Mock()

    cli.interpret_command('claim-review claim_type=retaliation')
    cli.interpret_command('execute-follow-up claim_type=retaliation follow_up_force=true')
    cli.interpret_command('export-complaint /tmp/out district="District of Columbia"')
    cli.interpret_command('adversarial-autopatch /tmp/patches num_sessions=2 max_turns=3')

    cli.claim_review.assert_called_once_with(['claim_type=retaliation'])
    cli.execute_follow_up.assert_called_once_with([
        'claim_type=retaliation',
        'follow_up_force=true',
    ])
    cli.export_complaint.assert_called_once_with([
        '/tmp/out',
        'district=District of Columbia',
    ])
    cli.adversarial_autopatch.assert_called_once_with([
        '/tmp/patches',
        'num_sessions=2',
        'max_turns=3',
    ])


def test_adversarial_autopatch_command_runs_demo_batch(monkeypatch, tmp_path):
    cli = _make_cli()
    captured = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        patch_path = tmp_path / 'autopatch.patch'
        summary_path = tmp_path / 'summary.json'
        patch_path.write_text('patch', encoding='utf-8')
        payload = {
            'num_results': 1,
            'report': {
                'average_score': 0.8,
                'score_trend': 'stable',
            },
            'runtime': {
                'mode': 'live',
                'preflight_warnings': [
                    'hf-router: Hugging Face router requires HF_TOKEN or HUGGINGFACE_HUB_TOKEN in the environment.',
                ],
            },
            'autopatch': {
                'success': True,
                'patch_path': str(patch_path),
                'patch_cid': 'demo-cli-cid',
                'metadata': {'demo': True},
            },
            'phase_mode': 'workflow',
            'phase_tasks': [
                {
                    'phase': 'intake_questioning',
                    'success': True,
                    'patch_path': str(tmp_path / 'intake.patch'),
                }
            ],
        }
        summary_path.write_text(json.dumps(payload), encoding='utf-8')
        return payload

    monkeypatch.setattr('applications.cli.run_adversarial_autopatch_batch', fake_runner)

    cli.adversarial_autopatch([
        str(tmp_path),
        'target_file=adversarial_harness/session.py',
        'num_sessions=2',
        'max_turns=4',
        'max_parallel=1',
        'phase_mode=workflow',
    ])

    assert captured['output_dir'] == str(tmp_path)
    assert captured['target_file'] == 'adversarial_harness/session.py'
    assert captured['num_sessions'] == 2
    assert captured['max_turns'] == 4
    assert captured['max_parallel'] == 1
    assert captured['phase_mode'] == 'workflow'
    assert captured['demo_backend'] is True
    rendered = cli.print_response.call_args[0][0]
    assert 'adversarial autopatch:' in rendered
    assert 'average_score: 0.8000' in rendered
    assert 'runtime_mode: live' in rendered
    assert 'phase_mode: workflow' in rendered
    assert 'phase_tasks: 1' in rendered
    assert '- intake_questioning: success=True' in rendered
    assert 'preflight_warnings:' in rendered
    assert 'HF_TOKEN or HUGGINGFACE_HUB_TOKEN' in rendered
    assert 'patch_cid: demo-cli-cid' in rendered

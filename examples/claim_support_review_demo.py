#!/usr/bin/env python3
"""
Example: Claim Support Review

Demonstrates how claim coverage matrix and claim coverage summary payloads can be
used to review support gaps across evidence and legal authorities.
"""


def main() -> None:
    print("=" * 70)
    print("Claim Support Review - Demonstration")
    print("=" * 70)
    print()

    print("This example demonstrates how to review claim support using:")
    print("1. claim_coverage_matrix for full per-element support detail")
    print("2. claim_coverage_summary for quick dashboard-style status counts")
    print("3. follow_up_plan for next-step retrieval and validation work")
    print()

    print("SCENARIO: Employment retaliation case")
    print("-" * 70)
    print("The plaintiff reported discrimination to HR and was terminated soon after.")
    print("The system has one authority-backed element, one evidence-backed element,")
    print("and one still-missing element.")
    print()

    claim_coverage_matrix = {
        'employment retaliation': {
            'claim_type': 'employment retaliation',
            'required_support_kinds': ['evidence', 'authority'],
            'total_elements': 3,
            'status_counts': {
                'covered': 1,
                'partially_supported': 1,
                'missing': 1,
            },
            'total_links': 3,
            'total_facts': 4,
            'support_by_kind': {
                'evidence': 2,
                'authority': 1,
            },
            'elements': [
                {
                    'element_id': 'employment_retaliation:1',
                    'element_text': 'Protected activity',
                    'status': 'covered',
                    'missing_support_kinds': [],
                    'links_by_kind': {
                        'evidence': [
                            {
                                'support_label': 'HR complaint email',
                                'record_summary': {
                                    'cid': 'QmEvidenceProtectedActivity',
                                    'parse_status': 'parsed',
                                    'graph_status': 'ready',
                                },
                                'graph_summary': {
                                    'entity_count': 3,
                                    'relationship_count': 2,
                                },
                            }
                        ],
                        'authority': [
                            {
                                'support_ref': '42 U.S.C. § 2000e-3',
                                'record_summary': {
                                    'citation': '42 U.S.C. § 2000e-3',
                                    'parse_status': 'fallback',
                                    'graph_status': 'available-fallback',
                                },
                                'graph_summary': {
                                    'entity_count': 2,
                                    'relationship_count': 2,
                                },
                            }
                        ],
                    },
                },
                {
                    'element_id': 'employment_retaliation:2',
                    'element_text': 'Adverse action',
                    'status': 'partially_supported',
                    'missing_support_kinds': ['authority'],
                    'links_by_kind': {
                        'evidence': [
                            {
                                'support_label': 'Termination notice',
                                'record_summary': {
                                    'cid': 'QmEvidenceTerminationNotice',
                                    'parse_status': 'parsed',
                                    'graph_status': 'ready',
                                },
                                'graph_summary': {
                                    'entity_count': 2,
                                    'relationship_count': 1,
                                },
                            }
                        ]
                    },
                },
                {
                    'element_id': 'employment_retaliation:3',
                    'element_text': 'Causal connection',
                    'status': 'missing',
                    'missing_support_kinds': ['evidence', 'authority'],
                    'links_by_kind': {},
                },
            ],
        }
    }

    claim_coverage_summary = {
        'employment retaliation': {
            'claim_type': 'employment retaliation',
            'total_elements': 3,
            'total_links': 3,
            'total_facts': 4,
            'support_by_kind': {
                'evidence': 2,
                'authority': 1,
            },
            'status_counts': {
                'covered': 1,
                'partially_supported': 1,
                'missing': 1,
            },
            'missing_elements': ['Causal connection'],
            'partially_supported_elements': ['Adverse action'],
        }
    }

    follow_up_plan = {
        'employment retaliation': {
            'task_count': 2,
            'tasks': [
                {
                    'claim_element': 'Causal connection',
                    'status': 'missing',
                    'missing_support_kinds': ['evidence', 'authority'],
                    'priority': 'high',
                    'recommended_action': 'retrieve_more_support',
                },
                {
                    'claim_element': 'Adverse action',
                    'status': 'partially_supported',
                    'missing_support_kinds': ['authority'],
                    'priority': 'medium',
                    'recommended_action': 'target_missing_support_kind',
                },
            ],
        }
    }

    claim_type = 'employment retaliation'
    coverage = claim_coverage_matrix[claim_type]
    summary = claim_coverage_summary[claim_type]
    follow_up = follow_up_plan[claim_type]

    print("STEP 1: Read the compact summary")
    print("-" * 70)
    print(f"Claim type: {claim_type}")
    print(f"Covered elements: {summary['status_counts']['covered']}")
    print(f"Partially supported elements: {summary['status_counts']['partially_supported']}")
    print(f"Missing elements: {summary['status_counts']['missing']}")
    print(f"Missing labels: {', '.join(summary['missing_elements'])}")
    print()

    print("STEP 2: Inspect the full coverage matrix")
    print("-" * 70)
    for element in coverage['elements']:
        print(f"{element['element_text']}: {element['status']}")
        if element['missing_support_kinds']:
            print(f"  Missing support kinds: {', '.join(element['missing_support_kinds'])}")
        for support_kind, links in element.get('links_by_kind', {}).items():
            print(f"  {support_kind} links: {len(links)}")
            for link in links:
                label = link.get('support_label') or link.get('support_ref') or 'support record'
                graph = link.get('graph_summary', {})
                print(f"    - {label}")
                print(
                    f"      graph entities={graph.get('entity_count', 0)} "
                    f"relationships={graph.get('relationship_count', 0)}"
                )
    print()

    print("STEP 3: Use follow-up planning to prioritize missing work")
    print("-" * 70)
    for task in follow_up['tasks']:
        print(f"{task['claim_element']}: priority={task['priority']} action={task['recommended_action']}")
        print(f"  missing support kinds: {', '.join(task['missing_support_kinds'])}")
    print()

    print("HOW THIS MAPS TO THE MEDIATOR API")
    print("-" * 70)
    print("matrix = mediator.get_claim_coverage_matrix(claim_type='employment retaliation')")
    print("summary = mediator.research_case_automatically()['claim_coverage_summary']['employment retaliation']")
    print("follow_up = mediator.get_claim_follow_up_plan(claim_type='employment retaliation')")
    print()

    print("=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)


if __name__ == '__main__':
    main()
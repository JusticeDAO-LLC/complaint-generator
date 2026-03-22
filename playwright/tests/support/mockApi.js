function buildReviewPayload(overrides = {}) {
  return {
    claim_type: 'retaliation',
    claim_coverage_summary: {
      retaliation: {
        status_counts: {
          covered: 1,
          partially_supported: 1,
          missing: 1,
        },
      },
    },
    claim_coverage_matrix: {
      retaliation: {
        elements: [
          {
            element_text: 'Protected activity',
            coverage_status: 'covered',
            support_summary: 'HR complaint email is linked.',
            supporting_sources: ['HR complaint email'],
          },
          {
            element_text: 'Adverse action',
            coverage_status: 'missing',
            support_summary: 'Termination document still needed.',
            supporting_sources: [],
          },
        ],
      },
    },
    follow_up_plan: {
      retaliation: {
        tasks: [
          {
            task_type: 'collect_document',
            title: 'Upload termination email',
            claim_element_id: 'retaliation:2',
            claim_element_text: 'Adverse action',
            support_kind: 'document',
            status: 'pending',
          },
        ],
      },
    },
    follow_up_plan_summary: {
      retaliation: {
        total_task_count: 1,
        completed_task_count: 0,
      },
    },
    follow_up_history: {
      retaliation: [],
    },
    follow_up_history_summary: {
      retaliation: {
        total_execution_count: 0,
      },
    },
    question_recommendations: {
      retaliation: [
        {
          question: 'What document shows the termination decision?',
          target_claim_element_id: 'retaliation:2',
        },
      ],
    },
    testimony_records: {
      retaliation: [],
    },
    testimony_summary: {
      retaliation: {
        record_count: 0,
      },
    },
    document_artifacts: {
      retaliation: [],
    },
    document_summary: {
      retaliation: {
        record_count: 0,
        linked_element_count: 0,
        total_chunk_count: 0,
        total_fact_count: 0,
        low_quality_record_count: 0,
        graph_ready_record_count: 0,
        parse_status_counts: {},
      },
    },
    intake_status: {
      readiness_status: 'warning',
      contradictions: [],
      criteria: [],
    },
    intake_case_summary: {
      candidate_claim_count: 1,
      canonical_fact_count: 2,
      proof_lead_count: 1,
      current_summary_snapshot: {
        candidate_claim_count: 1,
        canonical_fact_count: 2,
        proof_lead_count: 1,
      },
      complainant_summary_confirmation: {
        confirmed: false,
        status: 'pending',
        current_summary_snapshot: {
          candidate_claim_count: 1,
          canonical_fact_count: 2,
          proof_lead_count: 1,
        },
      },
    },
    review_links: {
      dashboard_url: '/claim-support-review?claim_type=retaliation&section=claims_for_relief',
    },
    ...overrides,
  };
}

function buildDocumentGenerationPayload() {
  return {
    generated_at: '2026-03-22T12:00:00Z',
    artifacts: {
      complaint_docx: {
        label: 'Complaint DOCX',
        type: 'docx',
        download_url: '/api/documents/download?path=/tmp/generated_documents/complaint.docx',
      },
      complaint_pdf: {
        label: 'Complaint PDF',
        type: 'pdf',
        download_url: '/api/documents/download?path=/tmp/generated_documents/complaint.pdf',
      },
    },
    draft: {
      court_header: 'UNITED STATES DISTRICT COURT\nNORTHERN DISTRICT OF CALIFORNIA',
      case_caption: {
        plaintiffs: ['Jane Doe'],
        defendants: ['Acme Corporation'],
        case_number: '26-cv-1234',
        document_title: 'COMPLAINT',
      },
      nature_of_action: [
        'This action challenges retaliation after protected civil-rights complaints.',
      ],
      summary_of_facts: [
        'Jane Doe reported discrimination to human resources.',
        'Acme terminated Jane Doe two days later.',
      ],
      factual_allegation_paragraphs: [
        'Jane Doe engaged in protected activity by reporting discrimination.',
        'Acme took materially adverse action by terminating Jane Doe.',
      ],
      legal_standards: [
        'Title VII prohibits retaliation for protected complaints.',
      ],
      claims_for_relief: [
        {
          claim_type: 'retaliation',
          count_title: 'First Claim for Relief: Retaliation',
          legal_standards: ['Protected activity, adverse action, and causation.'],
          supporting_facts: [
            'HR complaint email dated March 3, 2026.',
            'Termination notice dated March 5, 2026.',
          ],
          missing_elements: ['Need authenticated termination record in the evidence packet.'],
          supporting_exhibits: [
            { label: 'Exhibit A', title: 'HR complaint email' },
          ],
        },
      ],
      requested_relief: [
        'Back pay.',
        'Reinstatement or front pay.',
      ],
      signature_block: {
        signature_line: '__________________________',
        name: 'Jane Doe',
        title: 'Plaintiff, Pro Se',
      },
      verification: {
        title: 'Verification',
        text: 'I declare under penalty of perjury that the foregoing is true and correct.',
        signature_line: 'Jane Doe',
      },
      certificate_of_service: {
        title: 'Certificate of Service',
        text: 'I certify that I served the complaint on the defendants.',
      },
      draft_text: 'Jane Doe alleges that Acme retaliated against her after she reported discrimination.',
      exhibits: [
        {
          label: 'Exhibit A',
          title: 'HR complaint email',
          summary: 'Email reporting discrimination to HR.',
          link: 'https://example.org/exhibit-a',
        },
      ],
    },
    drafting_readiness: {
      claims: [
        {
          claim_type: 'retaliation',
          status: 'warning',
          warnings: ['Upload the termination email before filing.'],
        },
      ],
    },
    filing_checklist: [
      {
        title: 'Finalize evidence packet',
      },
    ],
    workflow_phase_plan: {
      prioritized_phase_name: 'document_generation',
      prioritized_phase_status: 'ready',
      recommended_actions: ['open_review_dashboard'],
    },
    review_links: {
      dashboard_url: '/claim-support-review?claim_type=retaliation&section=claims_for_relief',
      workflow_priority: {
        status: 'ready',
        title: 'Drafting is aligned with workflow guidance',
        description: 'The generated complaint is ready for coverage review and evidence follow-up.',
        action_label: 'Open Review Dashboard',
        action_url: '/claim-support-review?claim_type=retaliation&section=claims_for_relief',
        dashboard_url: '/claim-support-review?claim_type=retaliation&section=claims_for_relief',
        chip_labels: [
          'workflow phase: Document Generation',
          'phase status: Ready',
        ],
      },
      section_review_map: {
        claims_for_relief: {
          review_url: '/claim-support-review?claim_type=retaliation&section=claims_for_relief',
        },
      },
      intake_case_summary: {
        current_summary_snapshot: {
          candidate_claim_count: 1,
          canonical_fact_count: 2,
          proof_lead_count: 1,
        },
        complainant_summary_confirmation: {
          confirmed: false,
          status: 'pending',
          current_summary_snapshot: {
            candidate_claim_count: 1,
            canonical_fact_count: 2,
            proof_lead_count: 1,
          },
        },
      },
    },
    review_intent: {
      claim_type: 'retaliation',
      user_id: 'demo-user',
      section: 'claims_for_relief',
      follow_up_support_kind: 'authority',
      review_url: '/claim-support-review?claim_type=retaliation&section=claims_for_relief',
    },
  };
}

function buildSavedDocumentPayload(requestPayload) {
  const label = requestPayload.document_label || 'Document artifact';
  const elementText = requestPayload.claim_element || 'Claim element';
  return buildReviewPayload({
    document_artifacts: {
      retaliation: [
        {
          description: label,
          filename: requestPayload.filename || 'termination-email.txt',
          claim_element_text: elementText,
          evidence_type: 'document',
          parse_status: 'parsed',
          chunk_count: 2,
          fact_count: 1,
          graph_status: 'ready',
          timestamp: '2026-03-22T12:10:00Z',
          parsed_text_preview: requestPayload.document_text || 'Uploaded document text.',
          parse_metadata: {
            quality_tier: 'high',
          },
          chunk_previews: [
            { chunk_id: 'chunk-1', text: 'Jane Doe reported discrimination.' },
            { chunk_id: 'chunk-2', text: 'Acme terminated Jane Doe.' },
          ],
          fact_previews: [
            {
              fact_id: 'fact-1',
              text: 'Termination followed the HR complaint.',
              confidence: 0.93,
              source_chunk_ids: ['chunk-2'],
            },
          ],
          graph_preview: {
            entity_count: 2,
            relationship_count: 1,
            entities: [
              { id: 'entity-1', name: 'Jane Doe', type: 'person' },
              { id: 'entity-2', name: 'Acme Corporation', type: 'organization' },
            ],
            relationships: [
              { source: 'Jane Doe', target: 'Acme Corporation', type: 'employment' },
            ],
          },
        },
      ],
    },
    document_summary: {
      retaliation: {
        record_count: 1,
        linked_element_count: 1,
        total_chunk_count: 2,
        total_fact_count: 1,
        low_quality_record_count: 0,
        graph_ready_record_count: 1,
        parse_status_counts: {
          parsed: 1,
        },
      },
    },
  });
}

async function installMockApi(page, calls) {
  await page.route('**/api/documents/formal-complaint', async (route) => {
    const body = route.request().postDataJSON();
    calls.generate.push(body);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildDocumentGenerationPayload()),
    });
  });

  await page.route('**/api/claim-support/review', async (route) => {
    const body = route.request().postDataJSON();
    calls.review.push(body);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildReviewPayload()),
    });
  });

  await page.route('**/api/claim-support/save-document', async (route) => {
    const body = route.request().postDataJSON();
    calls.saveDocument.push(body);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildSavedDocumentPayload(body)),
    });
  });

  await page.route('**/api/claim-support/execute-follow-up', async (route) => {
    const body = route.request().postDataJSON();
    calls.execute.push(body);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        execution_result: {
          status: 'completed',
          execution_id: 42,
        },
        post_execution_review: buildReviewPayload({
          follow_up_history: {
            retaliation: [
              {
                execution_id: 42,
                status: 'completed',
                claim_element_id: 'retaliation:2',
                claim_element_text: 'Adverse action',
              },
            ],
          },
          follow_up_history_summary: {
            retaliation: {
              total_execution_count: 1,
            },
          },
        }),
      }),
    });
  });

  await page.route('**/api/claim-support/confirm-intake-summary', async (route) => {
    const body = route.request().postDataJSON();
    calls.confirm.push(body);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        confirmed: true,
        post_confirmation_review: buildReviewPayload({
          intake_case_summary: {
            complainant_summary_confirmation: {
              confirmed: true,
              status: 'confirmed',
              confirmation_source: body.confirmation_source || 'dashboard',
              confirmation_note: body.confirmation_note || null,
              confirmed_at: '2026-03-22T12:20:00Z',
              confirmed_summary_snapshot: {
                candidate_claim_count: 1,
                canonical_fact_count: 2,
                proof_lead_count: 1,
              },
            },
          },
        }),
      }),
    });
  });
}

async function installPageGuards(page) {
  await page.addInitScript(() => {
    window.alert = () => {};
  });
}

module.exports = {
  installMockApi,
  installPageGuards,
};

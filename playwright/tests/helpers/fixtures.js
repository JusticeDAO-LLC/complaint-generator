const documentGenerationResponse = {
  generated_at: '2026-03-22T12:00:00Z',
  artifacts: {
    txt: {
      filename: 'formal-complaint.txt',
      path: '/tmp/generated_documents/formal-complaint.txt',
      size_bytes: 2048,
      download_url: '/api/documents/download?path=/tmp/generated_documents/formal-complaint.txt',
    },
    packet: {
      filename: 'filing-packet.zip',
      path: '/tmp/generated_documents/filing-packet.zip',
      size_bytes: 4096,
      download_url: '/api/documents/download?path=/tmp/generated_documents/filing-packet.zip',
    },
  },
  review_intent: {
    claim_type: 'retaliation',
    user_id: 'demo-user',
    section: 'claims_for_relief',
    follow_up_support_kind: 'authority',
  },
  review_links: {
    dashboard_url: '/claim-support-review?claim_type=retaliation&user_id=demo-user&section=claims_for_relief&follow_up_support_kind=authority',
  },
  workflow_phase_plan: {
    prioritized_phase_name: 'document_generation',
    prioritized_phase_status: 'ready',
    primary_recommended_action: 'open_review_dashboard',
  },
  drafting_readiness: {
    status: 'ready',
    claims: [
      {
        claim_type: 'retaliation',
        status: 'ready',
        warnings: [],
      },
    ],
  },
  draft: {
    court_header: 'IN THE UNITED STATES DISTRICT COURT',
    case_caption: {
      plaintiffs: ['Jane Doe'],
      defendants: ['Acme Corporation'],
      case_number: '26-cv-1234',
      document_title: 'COMPLAINT',
    },
    nature_of_action: ['This civil action challenges unlawful retaliation.'],
    summary_of_facts: [
      'Jane Doe reported discrimination to human resources.',
      'Acme Corporation terminated Jane Doe days later.',
    ],
    factual_allegation_paragraphs: [
      'Jane Doe worked for Acme Corporation.',
      'After protected activity, Acme terminated Jane Doe.',
    ],
    legal_standards: ['Title VII prohibits retaliation against employees.'],
    claims_for_relief: [
      {
        claim_type: 'retaliation',
        count_title: 'First Claim for Relief',
        legal_standards: ['Protected activity and adverse action establish retaliation.'],
        supporting_facts: [
          'Plaintiff made a protected complaint to HR.',
          'Defendant terminated Plaintiff after the complaint.',
        ],
      },
    ],
    requested_relief: ['Back pay', 'Reinstatement', 'Compensatory damages'],
    draft_text: 'Plaintiff Jane Doe alleges retaliation in violation of Title VII.',
    exhibits: [
      {
        label: 'Exhibit 1',
        title: 'HR Complaint Email',
        summary: 'Email reporting discrimination.',
        link: 'https://example.test/hr-complaint',
      },
    ],
    signature_block: {
      signature_line: '/s/ Jane Doe',
      name: 'Jane Doe',
      title: 'Plaintiff, Pro Se',
      contact: 'jane@example.test',
    },
    verification: {
      title: 'Verification',
      text: 'I declare under penalty of perjury that the foregoing is true and correct.',
    },
    certificate_of_service: {
      title: 'Certificate of Service',
      text: 'I served the complaint by first-class mail.',
    },
  },
};

const reviewPayload = {
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
          element_id: 'retaliation:1',
          element_text: 'Protected activity',
          support_status: 'covered',
          supporting_evidence_count: 1,
          supporting_authority_count: 1,
          cited_authorities: ['Title VII'],
        },
        {
          element_id: 'retaliation:2',
          element_text: 'Adverse action',
          support_status: 'missing',
          missing_support_kinds: ['document'],
        },
      ],
    },
  },
  follow_up_plan: {
    retaliation: {
      tasks: [
        {
          execution_id: 7,
          claim_type: 'retaliation',
          claim_element_id: 'retaliation:2',
          claim_element_text: 'Adverse action',
          support_kind: 'document',
          section_focus: 'summary_of_facts',
          task_status: 'pending',
          summary: 'Collect the termination email and supporting timeline details.',
        },
      ],
    },
  },
  follow_up_plan_summary: {
    retaliation: {
      task_count: 1,
      pending_count: 1,
      completed_count: 0,
      archive_capture_count: 1,
      fallback_authority_count: 0,
      low_quality_record_count: 0,
      parse_quality_task_count: 0,
      supportive_authority_count: 1,
      adverse_authority_count: 0,
      unresolved_temporal_gap_count: 0,
      normalized_task_count: 1,
      follow_up_source_context_count: 1,
    },
  },
  follow_up_history: {
    retaliation: [
      {
        execution_id: 5,
        claim_element_id: 'retaliation:1',
        claim_element_text: 'Protected activity',
        support_kind: 'authority',
        status: 'completed',
        resolution_status: 'resolved_supported',
        notes: 'Authority support already attached.',
      },
    ],
  },
  follow_up_history_summary: {
    retaliation: {
      execution_count: 1,
      normalized_history_count: 1,
    },
  },
  question_recommendations: {
    retaliation: [
      {
        target_claim_element_id: 'retaliation:2',
        target_claim_element_text: 'Adverse action',
        question_text: 'When were you terminated after complaining to HR?',
        question_reason: 'This clarifies temporal proximity.',
        question_lane: 'testimony',
        expected_proof_gain: 'high',
        current_status: 'missing',
        supporting_evidence_summary: '1 HR complaint email on file',
      },
    ],
  },
  testimony_records: {
    retaliation: [
      {
        claim_element_id: 'retaliation:1',
        claim_element_text: 'Protected activity',
        timestamp: '2026-03-22T12:05:00Z',
        event_date: '2026-03-10',
        actor: 'Jane Doe',
        act: 'Reported discrimination',
        target: 'HR department',
        harm: 'Triggered retaliation sequence',
        firsthand_status: 'firsthand',
        source_confidence: 0.95,
        raw_narrative: 'I reported discrimination to HR and kept a copy of my complaint email.',
      },
    ],
  },
  testimony_summary: {
    retaliation: {
      record_count: 1,
      linked_element_count: 1,
      firsthand_status_counts: {
        firsthand: 1,
      },
      confidence_bucket_counts: {
        high: 1,
      },
    },
  },
  document_artifacts: {
    retaliation: [
      {
        description: 'HR complaint email',
        filename: 'hr-complaint-email.txt',
        timestamp: '2026-03-22T12:10:00Z',
        parse_status: 'parsed',
        chunk_count: 2,
        evidence_type: 'document',
        claim_element_text: 'Protected activity',
        graph_status: 'ready',
        fact_count: 1,
        parsed_text_preview: 'Email to HR reporting discrimination and requesting intervention.',
        fact_previews: [
          {
            fact_id: 'fact-1',
            text: 'Jane Doe reported discrimination to HR before termination.',
            quality_tier: 'high',
            confidence: 0.93,
            source_chunk_ids: ['chunk-1'],
          },
        ],
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
  claim_reasoning_review: {
    retaliation: {
      flagged_items: [],
    },
  },
  intake_status: {
    overall_status: 'warning',
    readiness_criteria: [
      {
        label: 'Document evidence collected',
        status: 'warning',
      },
    ],
    contradictions: [],
  },
  intake_case_summary: {
    current_summary_snapshot: {
      candidate_claim_count: 1,
      canonical_fact_count: 2,
      proof_lead_count: 1,
    },
  },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

async function installCommonMocks(page, recorder = {}, options = {}) {
  const documentResponses = Array.isArray(options.documentResponses) && options.documentResponses.length
    ? options.documentResponses.map((item) => clone(item))
    : [clone(documentGenerationResponse)];

  await page.addInitScript(() => {
    window.alert = () => {};
  });

  await page.route('**/api/documents/formal-complaint', async (route) => {
    const payload = route.request().postDataJSON();
    recorder.documentRequest = payload;
    if (!Array.isArray(recorder.documentRequests)) {
      recorder.documentRequests = [];
    }
    recorder.documentRequests.push(payload);
    const nextResponse = documentResponses.length > 1
      ? documentResponses.shift()
      : clone(documentResponses[0]);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(nextResponse),
    });
  });

  await page.route('**/api/claim-support/review', async (route) => {
    recorder.reviewRequest = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(clone(reviewPayload)),
    });
  });

  await page.route('**/api/claim-support/save-document', async (route) => {
    recorder.saveDocumentRequest = route.request().postDataJSON();
    const payload = clone(reviewPayload);
    payload.document_artifacts.retaliation = [
      {
        claim_element_id: 'retaliation:2',
        document_label: 'Termination Email',
        filename: 'termination-email.txt',
        evidence_type: 'document',
        created_at: '2026-03-22T12:30:00Z',
      },
    ];
    payload.document_summary.retaliation = {
      artifact_count: 1,
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    });
  });

  await page.route('**/api/claim-support/save-testimony', async (route) => {
    recorder.saveTestimonyRequest = route.request().postDataJSON();
    const payload = clone(reviewPayload);
    payload.testimony_records.retaliation = [
      {
        claim_element_id: 'retaliation:2',
        claim_element_text: 'Adverse action',
        timestamp: '2026-03-22T12:20:00Z',
        event_date: '2026-03-12',
        actor: 'Acme manager',
        act: 'Termination',
        target: 'Jane Doe',
        harm: 'Lost employment',
        firsthand_status: 'firsthand',
        source_confidence: 0.9,
        raw_narrative: 'My manager terminated me two days after I complained to HR.',
      },
    ];
    payload.testimony_summary.retaliation = {
      record_count: 1,
      linked_element_count: 1,
      firsthand_status_counts: {
        firsthand: 1,
      },
      confidence_bucket_counts: {
        high: 1,
      },
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        recorded: true,
        post_save_review: payload,
      }),
    });
  });

  await page.route('**/api/claim-support/execute-follow-up', async (route) => {
    recorder.executeRequest = route.request().postDataJSON();
    const payload = clone(reviewPayload);
    payload.follow_up_history.retaliation.unshift({
      execution_id: 8,
      claim_element_id: 'retaliation:2',
      claim_element_text: 'Adverse action',
      support_kind: 'document',
      status: 'completed',
      resolution_status: 'resolved_supported',
      notes: 'Termination email attached during execution.',
    });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        execution_id: 8,
        outcome_status: 'completed',
        notes: 'Follow-up execution completed.',
        post_execution_review: payload,
      }),
    });
  });

  await page.route('**/api/claim-support/confirm-intake-summary', async (route) => {
    recorder.confirmRequest = route.request().postDataJSON();
    const payload = clone(reviewPayload);
    payload.intake_case_summary.complainant_summary_confirmation = {
      confirmed: true,
      status: 'confirmed',
      confirmation_source: 'dashboard',
      confirmed_at: '2026-03-22T12:45:00Z',
      current_summary_snapshot: {
        candidate_claim_count: 1,
        canonical_fact_count: 2,
        proof_lead_count: 1,
      },
      confirmed_summary_snapshot: {
        candidate_claim_count: 1,
        canonical_fact_count: 2,
        proof_lead_count: 1,
      },
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        confirmed: true,
        post_confirmation_review: payload,
      }),
    });
  });
}

module.exports = {
  documentGenerationResponse,
  reviewPayload,
  installCommonMocks,
};

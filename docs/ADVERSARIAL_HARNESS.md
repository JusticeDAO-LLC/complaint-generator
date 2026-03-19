# Adversarial Test Harness and Optimizer

## Overview

The adversarial test harness is a system for optimizing the mediator's question generation capabilities using LLM-based agents in an adversarial setup. It consists of three main agents:

1. **Complainant (LLM)**: Generates complaints and responds to questions
2. **Mediator (System Under Test)**: Processes complaints and asks questions
3. **Critic (LLM)**: Evaluates the quality of mediator-complainant interactions

The system uses the LLM router for parallel batch processing and provides optimization recommendations based on critic feedback.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Seed Complaint Library                     │
│         (Templates + Pre-defined Complaint Scenarios)        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Adversarial Harness                         │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Parallel Session Executor (LLM Router)            │     │
│  │  - Runs multiple sessions concurrently             │     │
│  │  - Handles failures and retries                    │     │
│  │  - Aggregates results                              │     │
│  └────────────────────────────────────────────────────┘     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────────┐
         │    Adversarial Session            │
         │  ┌─────────────────────────────┐  │
         │  │  1. Complainant (LLM)       │  │
         │  │     - Generates complaint   │  │
         │  │     - Answers questions     │  │
         │  └─────────────────────────────┘  │
         │            ↕                       │
         │  ┌─────────────────────────────┐  │
         │  │  2. Mediator (SUT)          │  │
         │  │     - Processes complaint   │  │
         │  │     - Asks questions        │  │
         │  └─────────────────────────────┘  │
         │            ↓                       │
         │  ┌─────────────────────────────┐  │
         │  │  3. Critic (LLM)            │  │
         │  │     - Evaluates interaction │  │
         │  │     - Scores quality        │  │
         │  └─────────────────────────────┘  │
         └───────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       Optimizer                              │
│  - Analyzes critic scores across sessions                   │
│  - Identifies patterns and trends                           │
│  - Generates optimization recommendations                   │
│  - Tracks improvement over time                             │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Complainant (`adversarial_harness/complainant.py`)

**Purpose**: LLM-based agent that simulates a real complainant.

**Features**:
- Generates initial complaints from seed data
- Responds to mediator questions based on context
- Simulates different personalities (cooperative, defensive, vague, etc.)
- Maintains conversation history

**Classes**:
- `ComplaintContext`: Context information for a complaint
- `Complainant`: Main complainant agent
- `ComplaintGenerator`: Generates complaint variations

**Example**:
```python
backend = LLMRouterBackend(...)
complainant = Complainant(backend, personality="cooperative")

context = ComplaintContext(
    complaint_type="employment_discrimination",
    key_facts={'employer': 'Acme Corp', 'action': 'terminated'}
)
complainant.set_context(context)

# Generate initial complaint
complaint = complainant.generate_initial_complaint(seed_data)

# Respond to questions
response = complainant.respond_to_question("When did this occur?")
```

### 2. Critic (`adversarial_harness/critic.py`)

**Purpose**: LLM-based evaluator that assesses mediator performance.

**Evaluation Criteria**:
- **Question Quality** (0-1): How well-crafted are the questions?
- **Information Extraction** (0-1): How effectively is information gathered?
- **Empathy** (0-1): How empathetic is the interaction?
- **Efficiency** (0-1): How efficiently is information gathered?
- **Coverage** (0-1): How comprehensively are topics covered?

**Classes**:
- `CriticScore`: Structured evaluation score with feedback
- `Critic`: Main critic agent

**Example**:
```python
critic = Critic(llm_backend)

score = critic.evaluate_session(
    initial_complaint=complaint_text,
    conversation_history=conversation,
    final_state=mediator_state,
    context=ground_truth
)

print(f"Overall score: {score.overall_score:.3f}")
print(f"Strengths: {score.strengths}")
print(f"Weaknesses: {score.weaknesses}")
```

### 3. Adversarial Session (`adversarial_harness/session.py`)

**Purpose**: Manages a single adversarial training episode.

**Workflow**:
1. Complainant generates initial complaint from seed
2. Mediator processes complaint and asks questions
3. Complainant responds to questions
4. Repeat until convergence or max turns
5. Critic evaluates the complete session

**Classes**:
- `SessionResult`: Complete session data and results
- `AdversarialSession`: Session orchestrator

**Example**:
```python
session = AdversarialSession(
    session_id="session_001",
    complainant=complainant,
    mediator=mediator,
    critic=critic,
    max_turns=10
)

result = session.run(seed_complaint)
print(f"Score: {result.critic_score.overall_score:.3f}")
print(f"Questions asked: {result.num_questions}")
```

### 4. Seed Complaint Library (`adversarial_harness/seed_complaints.py`)

**Purpose**: Provides templates and seed data for generating diverse test scenarios.

**Templates**:
- Employment discrimination
- Housing discrimination
- Wrongful termination
- Consumer fraud
- (Extensible for more types)

**Classes**:
- `ComplaintTemplate`: Reusable complaint template
- `SeedComplaintLibrary`: Library of templates and seeds

**Example**:
```python
library = SeedComplaintLibrary()

# Get pre-defined seeds
seeds = library.get_seed_complaints(count=10)

# Create from template
template = library.get_template('employment_discrimination_1')
seed = template.instantiate({
    'employer': 'Tech Corp',
    'position': 'Engineer',
    'protected_class': 'race',
    'discriminatory_action': 'passed over for promotion'
})
```

### 5. Adversarial Harness (`adversarial_harness/harness.py`)

**Purpose**: Orchestrates multiple sessions with parallel execution.

**Features**:
- Parallel execution using thread pool
- Progress tracking
- Result aggregation
- Failure handling and retry
- Statistics generation

**Classes**:
- `AdversarialHarness`: Main orchestrator

**Example**:
```python
harness = AdversarialHarness(
    llm_backend_complainant=complainant_backend,
    llm_backend_critic=critic_backend,
    mediator_factory=lambda: Mediator([backend]),
    max_parallel=4
)

# Run batch of sessions
results = harness.run_batch(
    num_sessions=20,
    max_turns_per_session=10
)

# Get statistics
stats = harness.get_statistics()
print(f"Average score: {stats['average_score']:.3f}")
print(f"Success rate: {stats['successful_sessions']}/{stats['total_sessions']}")
```

### 6. Optimizer (`adversarial_harness/optimizer.py`)

**Purpose**: Analyzes critic feedback and provides optimization recommendations.

**Analysis**:
- Aggregates scores across sessions
- Identifies patterns in successes and failures
- Tracks trends over time
- Generates actionable recommendations
- Prioritizes improvements
- Summarizes weakest uncovered intake objectives
- Recommends likely patch-target files based on those intake gaps

**Classes**:
- `OptimizationReport`: Comprehensive optimization insights
- `Optimizer`: Analyzer and recommendation engine

**Example**:
```python
optimizer = Optimizer()

report = optimizer.analyze(session_results)

print(f"Average score: {report.average_score:.3f}")
print(f"Trend: {report.score_trend}")

print("Priority improvements:")
for improvement in report.priority_improvements:
    print(f"  - {improvement}")

print("Recommendations:")
for rec in report.recommendations:
    print(f"  - {rec}")
```

Recent intake-aware additions:

- The critic now records `intake_priority_expected`, `intake_priority_covered`, and `intake_priority_missing`.
- The optimizer aggregates those results into `intake_priority_performance`.
- Agentic autopatch task descriptions now include the weakest unresolved intake objectives.
- The optimizer can now recommend likely patch targets such as:
  - `adversarial_harness/session.py`
  - `mediator/mediator.py`
  - `adversarial_harness/complainant.py`

That recommendation path is consumed by `hacc_adversarial_runner.py`, which can either:

- print the requested, recommended, and selected autopatch scope for review, or
- use `--use-recommended-autopatch-targets` to let the optimizer's recommendation drive the autopatch target selection directly

## Usage

### Basic Workflow

```python
from adversarial_harness import (
    AdversarialHarness,
    Optimizer,
    SeedComplaintLibrary
)
from backends.llm_router_backend import LLMRouterBackend
from mediator.mediator import Mediator

# 1. Create LLM backends
complainant_backend = LLMRouterBackend('complainant', provider='openrouter')
critic_backend = LLMRouterBackend('critic', provider='openrouter')
mediator_backend = LLMRouterBackend('mediator', provider='openrouter')

# 2. Create mediator factory
def mediator_factory():
    return Mediator([mediator_backend])

# 3. Create harness
harness = AdversarialHarness(
    llm_backend_complainant=complainant_backend,
    llm_backend_critic=critic_backend,
    mediator_factory=mediator_factory,
    max_parallel=4
)

# 4. Run batch
results = harness.run_batch(num_sessions=20)

# 5. Analyze
optimizer = Optimizer()
report = optimizer.analyze(results)

# 6. Review and iterate
print(report.recommendations)
```

### Advanced: Custom Seeds and Personalities

```python
# Use custom seed complaints
custom_seeds = [
    {
        'type': 'employment_discrimination',
        'key_facts': {
            'employer': 'Custom Corp',
            'action': 'denied promotion',
            'protected_class': 'age'
        }
    }
]

# Test different complainant personalities
personalities = ['cooperative', 'defensive', 'vague', 'detailed', 'emotional']

results = harness.run_batch(
    num_sessions=10,
    seed_complaints=custom_seeds,
    personalities=personalities,
    max_turns_per_session=15
)
```

### Optimization Loop

```python
# Iterative improvement
for iteration in range(5):
    print(f"Iteration {iteration + 1}")
    
    # Run batch
    results = harness.run_batch(num_sessions=20)
    
    # Analyze
    report = optimizer.analyze(results)
    
    # Apply recommendations (manual or automated)
    if report.average_score < 0.7:
        print("Applying improvements...")
        # Adjust mediator prompts, logic, etc.
    
    # Track progress
    if len(optimizer.history) > 1:
        comparison = optimizer.compare_reports(
            optimizer.history[-2],
            optimizer.history[-1]
        )
        print(f"Score change: {comparison['score_change']:+.3f}")
```

## Integration with LLM Router

The harness uses the LLM router for parallel batch processing:

```python
from backends.llm_router_backend import LLMRouterBackend

# Configure LLM router
complainant_backend = LLMRouterBackend(
    'complainant',
    provider='openrouter',
    model='anthropic/claude-2'
)

critic_backend = LLMRouterBackend(
    'critic',
    provider='openrouter',
    model='anthropic/claude-2'
)

# The harness will use ThreadPoolExecutor to batch requests
# LLM router handles the actual API calls
```

## Output Formats

### Session Results

Results are saved as JSON:
```json
{
  "timestamp": "2024-01-01T00:00:00",
  "statistics": {
    "total_sessions": 20,
    "successful_sessions": 18,
    "average_score": 0.73,
    "score_distribution": {
      "0.6-0.8": 12,
      "0.8-1.0": 6
    }
  },
  "results": [...]
}
```

### Optimization Report

```json
{
  "timestamp": "2024-01-01T00:00:00",
  "num_sessions_analyzed": 18,
  "average_score": 0.73,
  "score_trend": "improving",
  "priority_improvements": [
    "Improve empathy: current avg 0.65",
    "Improve coverage: current avg 0.68"
  ],
  "recommendations": [...]
}
```

## Testing

Run tests:
```bash
pytest tests/test_adversarial_harness.py -v
```

Run example:
```bash
python examples/adversarial_harness_example.py
```

## Performance Considerations

- **Parallel Execution**: Use `max_parallel` to balance throughput vs resource usage
- **Session Duration**: Typical session takes 30-60 seconds with LLM
- **Batch Size**: Recommended 10-50 sessions per batch for meaningful statistics
- **LLM Costs**: Each session requires ~10-20 LLM calls (complainant + critic)

## Future Enhancements

Potential improvements:

1. **Reinforcement Learning**: Use critic scores as rewards for RL-based optimization
2. **Prompt Evolution**: Automatically evolve mediator prompts based on feedback
3. **Fine-tuning**: Collect high-quality sessions for fine-tuning
4. **Multi-Agent**: Add more agent types (witnesses, opposing counsel, etc.)
5. **Replay Analysis**: Detailed visualization of successful vs failed sessions
6. **A/B Testing**: Compare different mediator configurations
7. **Automated Improvement**: Automatically apply optimization recommendations

## References

- Adversarial training in NLP
- Reinforcement Learning from Human Feedback (RLHF)
- Multi-agent systems
- Prompt optimization techniques

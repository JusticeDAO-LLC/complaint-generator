# Agentic Optimizers API Reference

This document provides API reference for agentic optimizer classes in `ipfs_datasets_py.optimizers.agentic`.

## Table of Contents

1. [AgenticOptimizer](#agenticoptimizer)
2. [AgenticCLI](#agenticcli)
3. [Session Management](#session-management)
4. [Feedback Loops](#feedback-loops)
5. [Integration Examples](#integration-examples)

---

## AgenticOptimizer

**Module:** `ipfs_datasets_py.optimizers.agentic.optimizer`

Main optimization agent for iterative artifact improvement using LLM-based feedback.

### Initialization

```python
from ipfs_datasets_py.optimizers.agentic import AgenticOptimizer

optimizer = AgenticOptimizer(
    model: str = "gpt-5.3-codex",
    temperature: float = 0.7,
    max_iterations: int = 10,
    convergence_threshold: float = 0.95,
    enable_explanations: bool = True
)
```

**Parameters:**
- `model` (str): LLM model to use. Default: "gpt-5.3-codex"
- `temperature` (float): Generation temperature [0, 2]. Default: 0.7
- `max_iterations` (int): Maximum optimization iterations. Default: 10
- `convergence_threshold` (float): Quality threshold for early stopping [0, 1]. Default: 0.95
- `enable_explanations` (bool): Include reasoning in feedback. Default: True

### Core Methods

#### optimize(artifact: Any, objective: str, initial_feedback: str = None) → Dict[str, Any]

Run optimization loop to improve artifact toward objective.

```python
result = optimizer.optimize(
    artifact="Initial complaint text",
    objective="Maximize legal strength while maintaining professionalism",
    initial_feedback="The complaint needs more specific evidence"
)

# Returns:
# {
#     'final_artifact': "Improved complaint...",
#     'quality_score': 0.92,
#     'iterations': 5,
#     'feedback_history': [...],
#     'converged': True
# }
```

**Parameters:**
- `artifact` (Any): Initial artifact to optimize (usually text)
- `objective` (str): Optimization objective
- `initial_feedback` (str, optional): Initial system feedback. Default: None

**Returns:**
- Dict[str, Any]: Optimization result with:
  - `final_artifact`: Optimized artifact
  - `quality_score`: Final quality score [0, 1]
  - `iterations`: Number of iterations run
  - `feedback_history`: Feedback from each iteration
  - `converged`: Whether early stopping occurred

**Raises:**
- `ValueError`: If artifact or objective is empty

#### optimize_with_rubric(artifact: Any, rubric: Dict[str, float]) → Dict[str, Any]

Optimize artifact using multi-dimensional rubric.

```python
rubric = {
    'legal_strength': 0.3,  # 30% weight
    'clarity': 0.3,          # 30% weight
    'evidence_quality': 0.4  # 40% weight
}

result = optimizer.optimize_with_rubric(artifact, rubric)
```

**Parameters:**
- `artifact` (Any): Artifact to optimize
- `rubric` (Dict[str, float]): Weighted evaluation criteria

**Returns:**
- Dict[str, Any]: Optimization result with rubric breakdown

#### generate_feedback(artifact: Any, criteria: List[str]) → str

Generate detailed feedback on artifact.

```python
criteria = [
    "Is the complaint specific and detailed?",
    "Are damages clearly quantified?",
    "Is the legal basis strong?",
    "Is the tone appropriate?"
]

feedback = optimizer.generate_feedback(artifact, criteria)
# Returns: "The complaint is well-structured but needs more specific dates..."
```

**Parameters:**
- `artifact` (Any): Artifact to evaluate
- `criteria` (List[str]): Evaluation criteria

**Returns:**
- str: Detailed feedback

#### score_artifact(artifact: Any, dimensions: List[str] = None) → Dict[str, float]

Score artifact across multiple dimensions.

```python
dimensions = ["clarity", "completeness", "legality", "persuasiveness"]
scores = optimizer.score_artifact(artifact, dimensions)
# Returns: {
#     'clarity': 0.85,
#     'completeness': 0.78,
#     'legality': 0.92,
#     'persuasiveness': 0.81,
#     'overall': 0.84
# }
```

**Parameters:**
- `artifact` (Any): Artifact to score
- `dimensions` (List[str], optional): Scoring dimensions. Default: None (uses standard)

**Returns:**
- Dict[str, float]: Scores for each dimension plus overall

---

## AgenticCLI

**Module:** `ipfs_datasets_py.optimizers.agentic.cli`

Command-line interface for agentic optimization.

### CLI Commands

#### optimize

Optimize an artifact from command line.

```bash
python -m ipfs_datasets_py.optimizers.agentic.cli optimize \
    --input artifact.txt \
    --objective "Maximize legal strength" \
    --output optimized.txt \
    --model gpt-5.3-codex \
    --iterations 5
```

**Options:**
- `--input` (str): Input file path
- `--objective` (str): Optimization objective
- `--output` (str): Output file path
- `--model` (str): LLM model. Default: "gpt-5.3-codex"
- `--iterations` (int): Max iterations. Default: 10
- `--temperature` (float): Model temperature. Default: 0.7
- `--threshold` (float): Convergence threshold. Default: 0.95
- `--json` (bool): Output as JSON. Default: False

**Returns:**
Output file with optimized artifact and metadata.

#### evaluate

Evaluate artifact quality from command line.

```bash
python -m ipfs_datasets_py.optimizers.agentic.cli evaluate \
    --input artifact.txt \
    --criteria legal_strength clarity completeness \
    --output evaluation.json
```

**Options:**
- `--input` (str): Input file path
- `--criteria` (List[str]): Evaluation criteria
- `--output` (str): Output file for results
- `--model` (str): LLM model. Default: "gpt-5.3-codex"
- `--format` (str): Output format (json/yaml/text). Default: "json"

#### batch

Batch optimize multiple artifacts.

```bash
python -m ipfs_datasets_py.optimizers.agentic.cli batch \
    --input-dir ./complaints \
    --output-dir ./optimized \
    --objective "Maximize legal strength" \
    --parallel 4
```

**Options:**
- `--input-dir` (str): Input directory
- `--output-dir` (str): Output directory
- `--objective` (str): Optimization objective
- `--parallel` (int): Parallel workers. Default: 1
- `--filter` (str): File regex filter. Default: "*.txt"
- `--skip-errors` (bool): Continue on errors. Default: False

---

## Session Management

**Module:** `ipfs_datasets_py.optimizers.agentic.session`

Manage optimization sessions with history and checkpointing.

### Session Class

```python
from ipfs_datasets_py.optimizers.agentic import Session

session = Session(
    session_id: str = None,
    checkpoint_dir: str = ".checkpoints",
    auto_save: bool = True
)
```

**Parameters:**
- `session_id` (str, optional): Session identifier. Default: Auto-generated
- `checkpoint_dir` (str): Directory for saving checkpoints. Default: ".checkpoints"
- `auto_save` (bool): Auto-save after each iteration. Default: True

### Methods

#### start_optimization(artifact: Any, objective: str) → str

Start a new optimization session.

```python
session_id = session.start_optimization(
    artifact="Initial text...",
    objective="Improve complaint"
)
```

**Parameters:**
- `artifact` (Any): Initial artifact
- `objective` (str): Optimization objective

**Returns:**
- str: Session ID

#### add_iteration(feedback: str, updated_artifact: Any, score: float) → None

Record an optimization iteration.

```python
session.add_iteration(
    feedback="Improved specificity and dates",
    updated_artifact="Updated text...",
    score=0.87
)
```

**Parameters:**
- `feedback` (str): Feedback from this iteration
- `updated_artifact` (Any): Updated artifact
- `score` (float): Quality score [0, 1]

#### checkpoint() → str

Save current session state to checkpoint.

```python
checkpoint_path = session.checkpoint()
# Returns: ".checkpoints/session_123/iteration_5.pkl"
```

**Returns:**
- str: Path to checkpoint file

#### load_checkpoint(checkpoint_path: str) → None

Load session from checkpoint.

```python
session.load_checkpoint(".checkpoints/session_123/iteration_5.pkl")
```

**Parameters:**
- `checkpoint_path` (str): Path to checkpoint file

**Raises:**
- `FileNotFoundError`: If checkpoint doesn't exist

#### get_history() → List[Dict[str, Any]]

Get full iteration history.

```python
history = session.get_history()
# Returns: [
#     {'iteration': 1, 'feedback': '...', 'score': 0.75},
#     {'iteration': 2, 'feedback': '...', 'score': 0.82},
#     ...
# ]
```

**Returns:**
- List[Dict[str, Any]]: Iteration records

#### export_session(format: str = "json") → str

Export session data in specified format.

```python
json_data = session.export_session(format="json")
```

**Parameters:**
- `format` (str): Export format (json/yaml/csv). Default: "json"

**Returns:**
- str: Formatted session data

---

## Feedback Loops

**Module:** `ipfs_datasets_py.optimizers.agentic.feedback`

Manage feedback collection and processing.

### FeedbackLoop Class

```python
from ipfs_datasets_py.optimizers.agentic import FeedbackLoop

feedback_loop = FeedbackLoop(
    model: str = "gpt-5.3-codex",
    max_feedback_rounds: int = 5,
    aggregation_strategy: str = "weighted_average"
)
```

**Parameters:**
- `model` (str): LLM model. Default: "gpt-5.3-codex"
- `max_feedback_rounds` (int): Max feedback cycles. Default: 5
- `aggregation_strategy` (str): How to aggregate feedback. Default: "weighted_average"

### Methods

#### collect_feedback(artifact: Any, sources: List[str]) → Dict[str, str]

Collect feedback from multiple sources.

```python
feedback = feedback_loop.collect_feedback(
    artifact="Text to evaluate",
    sources=["legal_expert", "clarity_checker", "completeness_validator"]
)
# Returns: {
#     'legal_expert': "The legal basis is strong...",
#     'clarity_checker': "Some phrasing is complex...",
#     'completeness_validator': "Missing dates and amounts..."
# }
```

**Parameters:**
- `artifact` (Any): Artifact to evaluate
- `sources` (List[str]): Feedback sources/perspectives

**Returns:**
- Dict[str, str]: Feedback from each source

#### aggregate_feedback(feedback: Dict[str, str]) → str

Combine multiple feedback sources into coherent guidance.

```python
aggregated = feedback_loop.aggregate_feedback(feedback)
# Returns: "Primary issues: missing specific dates, improve legal clarity..."
```

**Parameters:**
- `feedback` (Dict[str, str]): Feedback from multiple sources

**Returns:**
- str: Aggregated feedback

#### apply_feedback(artifact: Any, feedback: str) → Any

Apply feedback to generate improved artifact.

```python
improved = feedback_loop.apply_feedback(artifact, feedback)
```

**Parameters:**
- `artifact` (Any): Current artifact
- `feedback` (str): Feedback to apply

**Returns:**
- Any: Improved artifact

#### should_iterate(current_score: float, max_iterations: int, iteration_count: int) → bool

Determine if iteration should continue.

```python
if feedback_loop.should_iterate(current_score=0.82, 
                                max_iterations=10, 
                                iteration_count=3):
    continue_optimization()
```

**Parameters:**
- `current_score` (float): Current quality score [0, 1]
- `max_iterations` (int): Maximum allowed iterations
- `iteration_count` (int): Current iteration number

**Returns:**
- bool: True if optimization should continue

---

## Integration Examples

### Example 1: Basic Optimization

```python
from ipfs_datasets_py.optimizers.agentic import AgenticOptimizer

# Initialize optimizer
optimizer = AgenticOptimizer(
    model="gpt-5.3-codex",
    temperature=0.7,
    max_iterations=5
)

# Define artifact and objective
complaint = """
The defendant violated my rights. They did this thing that was wrong.
I deserve compensation.
"""

objective = "Create a legally strong complaint document"

# Run optimization
result = optimizer.optimize(complaint, objective)

# Use result
print(f"Final quality score: {result['quality_score']}")
print(f"Iterations: {result['iterations']}")
print(f"\nOptimized artifact:\n{result['final_artifact']}")
```

### Example 2: Multi-Dimensional Rubric

```python
from ipfs_datasets_py.optimizers.agentic import AgenticOptimizer

optimizer = AgenticOptimizer()

# Define weighted rubric
rubric = {
    'legal_strength': 0.4,      # 40% weight
    'factual_accuracy': 0.3,    # 30% weight
    'clarity': 0.2,             # 20% weight
    'professionalism': 0.1      # 10% weight
}

# Optimize with rubric
result = optimizer.optimize_with_rubric(complaint, rubric)

# Extract scores
scores = result['rubric_scores']
print(f"Legal strength: {scores['legal_strength']}")
print(f"Factual accuracy: {scores['factual_accuracy']}")
print(f"Clarity: {scores['clarity']}")
print(f"Professionalism: {scores['professionalism']}")
print(f"Overall: {result['quality_score']}")
```

### Example 3: Session-Based Optimization

```python
from ipfs_datasets_py.optimizers.agentic import AgenticOptimizer, Session

# Create session
session = Session(checkpoint_dir=".optimization_checkpoints")

# Initialize optimizer
optimizer = AgenticOptimizer()

# Start optimization
session_id = session.start_optimization(
    artifact=complaint,
    objective="Maximize legal efficacy"
)

try:
    current_artifact = complaint
    for i in range(5):
        # Run optimization iteration
        feedback = optimizer.generate_feedback(
            current_artifact,
            criteria=["legal_strength", "specificity", "evidence_quality"]
        )
        
        # Generate improved version
        improved = optimizer.optimize(
            current_artifact,
            objective="Incorporate feedback",
            initial_feedback=feedback
        )
        
        # Record iteration
        score = improved['quality_score']
        session.add_iteration(
            feedback=feedback,
            updated_artifact=improved['final_artifact'],
            score=score
        )
        
        # Checkpoint progress
        session.checkpoint()
        
        current_artifact = improved['final_artifact']
        
        if score > 0.95:
            print(f"Converged at iteration {i+1}")
            break
    
    # Export results
    history = session.get_history()
    session.export_session(format="json")

except Exception as e:
    print(f"Error: {e}")
    # Session auto-saves, can recover from checkpoint
```

### Example 4: Feedback Loop

```python
from ipfs_datasets_py.optimizers.agentic import FeedbackLoop, AgenticOptimizer

# Create feedback loop
feedback_loop = FeedbackLoop(
    model="gpt-5.3-codex",
    max_feedback_rounds=3
)

# Initialize optimizer
optimizer = AgenticOptimizer()

# Start optimization
artifact = complaint
max_iterations = 5

for iteration in range(max_iterations):
    # Collect multi-source feedback
    feedback_dict = feedback_loop.collect_feedback(
        artifact,
        sources=[
            "legal_expert",
            "clarity_specialist",
            "completeness_validator"
        ]
    )
    
    # Aggregate feedback
    feedback = feedback_loop.aggregate_feedback(feedback_dict)
    
    # Check if iteration should continue
    current_score = optimizer.score_artifact(artifact)['overall']
    if not feedback_loop.should_iterate(current_score, max_iterations, iteration):
        print(f"Stopping at iteration {iteration}")
        break
    
    # Apply feedback
    artifact = feedback_loop.apply_feedback(artifact, feedback)
    
    print(f"Iteration {iteration+1}: {current_score:.2f}")

print(f"\nFinal artifact:\n{artifact}")
```

### Example 5: CLI Batch Processing

```bash
# Optimize multiple complaints in parallel
python -m ipfs_datasets_py.optimizers.agentic.cli batch \
    --input-dir ./input_complaints \
    --output-dir ./optimized_complaints \
    --objective "Maximize legal strength while maintaining professionalism" \
    --parallel 4 \
    --iterations 3 \
    --model gpt-4

# Evaluate optimized complaints
python -m ipfs_datasets_py.optimizers.agentic.cli evaluate \
    --input ./optimized_complaints \
    --criteria \
        legal_strength \
        clarity \
        completeness \
        evidence_quality \
    --output evaluation_results.json
```

### Example 6: Streaming Optimization

```python
from ipfs_datasets_py.optimizers.agentic import AgenticOptimizer

optimizer = AgenticOptimizer(enable_explanations=True)

# Optimize with streaming feedback
artifact = complaint

print("Starting optimization...\n")

result = optimizer.optimize(
    artifact=artifact,
    objective="Create compelling legal complaint",
    initial_feedback=None
)

# Stream iterations
for i, feedback in enumerate(result['feedback_history'], 1):
    print(f"Iteration {i} feedback:")
    print(f"  {feedback}\n")

print(f"Final score: {result['quality_score']}")
print(f"Converged: {result['converged']}")
print(f"\nOptimized text:")
print(result['final_artifact'])
```

---

## Error Handling

### Common Errors and Solutions

#### ValueError: Empty artifact

```python
# Problem
result = optimizer.optimize("", "Optimize this")  # Error!

# Solution
artifact = artifact.strip()
if not artifact:
    raise ValueError("Artifact cannot be empty")
result = optimizer.optimize(artifact, objective)
```

#### TimeoutError: LLM call exceeded timeout

```python
# Problem: LLM hanging on complex artifact
# Solution: Increase timeout or split artifact

try:
    result = optimizer.optimize(large_artifact, objective)
except TimeoutError:
    # Split into chunks
    parts = split_artifact(large_artifact, max_size=5000)
    results = [optimizer.optimize(part, objective) for part in parts]
    result = combine_results(results)
```

#### RuntimeError: API rate limit exceeded

```python
# Solution: Implement delay

import time

for artifact in artifacts:
    try:
        result = optimizer.optimize(artifact, objective)
    except RuntimeError as e:
        if "rate limit" in str(e):
            print("Rate limited, waiting 60s...")
            time.sleep(60)
            result = optimizer.optimize(artifact, objective)
        else:
            raise
```

---

## Performance Tips

1. **Batch Processing**: Use CLI `batch` command for multiple artifacts
2. **Caching**: Enable caching to avoid re-evaluating identical artifacts
3. **Model Selection**: Use a lighter router-backed model for fast feedback and `gpt-5.3-codex` for higher-quality reasoning
4. **Convergence**: Set appropriate `convergence_threshold` to stop early when quality plateaus
5. **Checkpointing**: Enable `auto_save` for long-running optimizations

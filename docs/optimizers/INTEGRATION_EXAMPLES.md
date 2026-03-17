# GraphRAG Integration Examples

This guide provides practical integration examples for using the GraphRAG optimizer in various real-world scenarios.

Related guides:
- [Performance Tuning Guide](./PERFORMANCE_TUNING_GUIDE.md)
- [How To Add a New Optimizer](./HOW_TO_ADD_NEW_OPTIMIZER.md)
- [Sandboxed Prover Policy](./SANDBOXED_PROVER_POLICY.md)
- [Troubleshooting Dashboards](./TROUBLESHOOTING_DASHBOARDS.md)
- [Alerting Examples](./ALERTING_EXAMPLES.md)

## CLI Path Safety Policy

Optimizer CLIs validate user-supplied file paths through `_safe_resolve(...)`
helpers to block traversal into restricted system areas.

Restricted roots:
- `/proc`
- `/sys`
- `/dev`
- `/etc`

Current coverage:
- GraphRAG CLI: `optimizers/graphrag/cli_wrapper.py::_safe_resolve`
- Logic CLI: `optimizers/logic_theorem_optimizer/cli_wrapper.py::_safe_resolve`
- Tests: `tests/unit/optimizers/test_safe_resolve_path_traversal.py`

## Metrics Persistence Error Handling

Query metrics persistence emits structured error codes when write paths degrade:
- `QMETRICS_SERIALIZATION_ERROR`: metrics payload could not be serialized; fallback JSON payload was written.
- `QMETRICS_FALLBACK_WRITE_ERROR`: fallback write also failed; check logger output and metrics directory health.

Recommended operator flow:
1. Alert on repeated `QMETRICS_SERIALIZATION_ERROR` to catch schema/type drift in metrics payloads.
2. Treat any `QMETRICS_FALLBACK_WRITE_ERROR` as urgent storage/permissions incident for the metrics path.
3. Correlate spikes with deployment windows and changes to query metadata fields.

## Table of Contents

1. [FastAPI Web Service](#fastapi-web-service)
2. [Batch Document Processing](#batch-document-processing)
3. [CI/CD Integration](#cicd-integration)
4. [Flask REST API](#flask-rest-api)
5. [Command-Line Tool](#command-line-tool)
6. [Jupyter Notebook Analysis](#jupyter-notebook-analysis)
7. [Streaming Processing](#streaming-processing)
8. [Multi-Domain Pipeline](#multi-domain-pipeline)
9. [Semantic Entity Deduplication](#semantic-entity-deduplication)

## FastAPI Web Service

Complete REST API for ontology extraction with async support.

```python
"""
ontology_service.py - FastAPI service for ontology extraction
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import uvicorn
from enum import Enum

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyMediator,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
    ExtractionConfig,
)

app = FastAPI(title="GraphRAG Ontology Service", version="1.0.0")

# Global instances (reused across requests)
generator = OntologyGenerator(
    config=ExtractionConfig(
        confidence_threshold=0.6,
        max_entities=150,
        max_relationships=250,
    )
)
critic = OntologyCritic()
mediator = OntologyMediator(generator=generator, critic=critic, max_rounds=5)


class DomainEnum(str, Enum):
    legal = "legal"
    medical = "medical"
    business = "business"
    general = "general"


class StrategyEnum(str, Enum):
    rule_based = "rule_based"
    llm_fallback = "llm_fallback"
    pure_llm = "pure_llm"


class ExtractionRequest(BaseModel):
    text: str = Field(..., description="Input text to extract ontology from")
    domain: DomainEnum = Field(default=DomainEnum.general, description="Document domain")
    strategy: StrategyEnum = Field(default=StrategyEnum.rule_based, description="Extraction strategy")
    refine: bool = Field(default=False, description="Run refinement cycle")
    confidence_threshold: Optional[float] = Field(default=None, gt=0, lt=1, description="Confidence threshold override")


class ExtractionResponse(BaseModel):
    entities: List[Dict]
    relationships: List[Dict]
    metadata: Dict
    score: Optional[Dict] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    components: Dict


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "generator": "operational",
            "critic": "operational",
            "mediator": "operational",
        }
    }


@app.post("/extract", response_model=ExtractionResponse)
async def extract_ontology(request: ExtractionRequest):
    """
    Extract ontology from text.
    
    **Example**:
    ```
    curl -X POST "http://localhost:8000/extract" \\
      -H "Content-Type: application/json" \\
      -d '{
        "text": "Alice works for Acme Corp. She completes training annually.",
        "domain": "business",
        "strategy": "rule_based"
      }'
    ```
    """
    
    try:
        # Create context
        context = OntologyGenerationContext(
            data_source="api_request",
            data_type=DataType.TEXT,
            domain=request.domain.value,
            extraction_strategy=ExtractionStrategy[request.strategy.value.upper()],
        )
        
        # Override config if specified
        if request.confidence_threshold:
            generator.config.confidence_threshold = request.confidence_threshold
        
        if request.refine:
            # Run refinement cycle
            state = mediator.run_refinement_cycle(request.text, context)
            ontology = state['current_ontology']
            score = critic.evaluate_ontology(ontology, context, request.text)
            
            return ExtractionResponse(
                entities=ontology['entities'],
                relationships=ontology['relationships'],
                metadata={
                    'refinement_rounds': state['current_round'],
                    'final_score': score.overall,
                    'text_length': len(request.text),
                },
                score={
                    'overall': score.overall,
                    'completeness': score.completeness,
                    'consistency': score.consistency,
                    'clarity': score.clarity,
                }
            )
        else:
            # Single-shot extraction
            ontology = generator.generate_ontology(request.text, context)
            score = critic.evaluate_ontology(ontology, context, request.text)
            
            return ExtractionResponse(
                entities=ontology['entities'],
                relationships=ontology['relationships'],
                metadata={
                    'strategy': request.strategy.value,
                    'domain': request.domain.value,
                    'text_length': len(request.text),
                },
                score={
                    'overall': score.overall,
                    'completeness': score.completeness,
                    'consistency': score.consistency,
                },
            )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@app.post("/extract/async")
async def extract_ontology_async(request: ExtractionRequest, background_tasks: BackgroundTasks):
    """
    Asynchronous extraction for large documents.
    Returns job ID immediately, process in background.
    """
    import uuid
    
    job_id = str(uuid.uuid4())
    
    # Store job result (in production, use Redis or database)
    jobs = {}
    
    def process_extraction():
        context = OntologyGenerationContext(
            data_source="api_request_async",
            data_type=DataType.TEXT,
            domain=request.domain.value,
            extraction_strategy=ExtractionStrategy[request.strategy.value.upper()],
        )
        
        ontology = generator.generate_ontology(request.text, context)
        jobs[job_id] = {
            'status': 'completed',
            'result': ontology,
        }
    
    background_tasks.add_task(process_extraction)
    
    return {"job_id": job_id, "status": "processing"}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Check status of async extraction job."""
    # In production, retrieve from Redis or database
    jobs = {}  # Placeholder
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs[job_id]


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Usage**:
```bash
# Start server
python ontology_service.py

# Health check
curl http://localhost:8000/health

# Extract ontology
curl -X POST "http://localhost:8000/extract" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Alice is an employee of Acme Corp.",
    "domain": "business",
    "strategy": "rule_based",
    "refine": false
  }'
```

## Batch Document Processing

Process multiple documents efficiently with progress tracking.

```python
"""
batch_processor.py - Batch document processing with parallel execution
"""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict
import json
from tqdm import tqdm

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
)


class BatchProcessor:
    """Process multiple documents in batch with parallel execution."""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.generator = OntologyGenerator()
        self.critic = OntologyCritic()
    
    def process_directory(
        self,
        input_dir: Path,
        output_dir: Path,
        domain: str = "general",
        pattern: str = "*.txt",
    ) -> List[Dict]:
        """
        Process all files in directory matching pattern.
        
        Args:
            input_dir: Directory containing source files
            output_dir: Directory to save results
            domain: Document domain
            pattern: File pattern (glob)
        
        Returns:
            List of processing results
        """
        
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Find all matching files
        files = list(input_dir.glob(pattern))
        print(f"Found {len(files)} files to process")
        
        results = []
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(self._process_single_file, file, domain): file
                for file in files
            }
            
            # Process completed tasks with progress bar
            with tqdm(total=len(files), desc="Processing documents") as pbar:
                for future in as_completed(future_to_file):
                    file = future_to_file[future]
                    try:
                        result = future.result()
                        
                        # Save result
                        output_file = output_dir / f"{file.stem}_ontology.json"
                        with open(output_file, 'w') as f:
                            json.dump(result, f, indent=2, default=str)
                        
                        results.append({
                            'file': str(file),
                            'status': 'success',
                            'output': str(output_file),
                            'entities': len(result['ontology']['entities']),
                            'score': result['score']['overall'],
                        })
                    
                    except Exception as e:
                        results.append({
                            'file': str(file),
                            'status': 'error',
                            'error': str(e),
                        })
                    
                    pbar.update(1)
        
        # Generate summary report
        self._generate_summary(results, output_dir / "batch_summary.json")
        
        return results
    
    def _process_single_file(self, file: Path, domain: str) -> Dict:
        """Process a single file."""
        
        # Read text
        text = file.read_text(encoding='utf-8')
        
        # Create context
        context = OntologyGenerationContext(
            data_source=str(file),
            data_type=DataType.TEXT,
            domain=domain,
            extraction_strategy=ExtractionStrategy.RULE_BASED,
        )
        
        # Generate ontology
        ontology = self.generator.generate_ontology(text, context)
        
        # Evaluate
        score = self.critic.evaluate_ontology(ontology, context, text)
        
        return {
            'file': str(file),
            'ontology': ontology,
            'score': {
                'overall': score.overall,
                'completeness': score.completeness,
                'consistency': score.consistency,
            }
        }
    
    def _generate_summary(self, results: List[Dict], output_file: Path):
        """Generate batch processing summary."""
        
        successful = [r for r in results if r['status'] == 'success']
        failed = [r for r in results if r['status'] == 'error']
        
        summary = {
            'total_files': len(results),
            'successful': len(successful),
            'failed': len(failed),
            'average_entities': sum(r.get('entities', 0) for r in successful) / len(successful) if successful else 0,
            'average_score': sum(r.get('score', 0) for r in successful) / len(successful) if successful else 0,
            'failed_files': [r['file'] for r in failed],
        }
        
        with open(output_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\nBatch processing complete:")
        print(f"  Successful: {summary['successful']}/{summary['total_files']}")
        print(f"  Average entities: {summary['average_entities']:.1f}")
        print(f"  Average score: {summary['average_score']:.2f}")


# Usage
if __name__ == "__main__":
    processor = BatchProcessor(max_workers=4)
    
    results = processor.process_directory(
        input_dir=Path("./documents"),
        output_dir=Path("./ontologies"),
        domain="legal",
        pattern="*.txt",
    )
```

## CI/CD Integration

Integrate ontology extraction into GitHub Actions workflow.

**.github/workflows/ontology-extraction.yml**:
```yaml
name: Ontology Extraction

on:
  push:
    paths:
      - 'documents/**/*.txt'
  pull_request:
    paths:
      - 'documents/**/*.txt'

jobs:
  extract-ontologies:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -e ipfs_datasets_py
      
      - name: Extract ontologies from changed files
        run: python scripts/ci_extract_ontologies.py
      
      - name: Upload ontology artifacts
        uses: actions/upload-artifact@v3
        with:
          name: ontologies
          path: ontologies/*.json
      
      - name: Quality check
        run: python scripts/ci_quality_check.py
```

**scripts/ci_extract_ontologies.py**:
```python
"""
CI/CD script for extracting ontologies from changed documents.
"""

import os
import sys
import json
from pathlib import Path

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
)


def get_changed_files():
    """Get list of changed .txt files from git."""
    import subprocess
    
    # Get changed files in last commit
    result = subprocess.run(
        ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
        capture_output=True,
        text=True,
    )
    
    # Filter for .txt files in documents/
    changed_files = [
        f for f in result.stdout.split('\n')
        if f.startswith('documents/') and f.endswith('.txt')
    ]
    
    return changed_files


def main():
    generator = OntologyGenerator()
    critic = OntologyCritic()
    
    changed_files = get_changed_files()
    
    if not changed_files:
        print("No document changes detected")
        return 0
    
    print(f"Processing {len(changed_files)} changed documents")
    
    output_dir = Path("ontologies")
    output_dir.mkdir(exist_ok=True)
    
    results = []
    
    for file_path in changed_files:
        file = Path(file_path)
        
        if not file.exists():
            print(f"Skipping deleted file: {file}")
            continue
        
        text = file.read_text()
        
        context = OntologyGenerationContext(
            data_source=str(file),
            data_type=DataType.TEXT,
            domain="general",
            extraction_strategy=ExtractionStrategy.RULE_BASED,
        )
        
        ontology = generator.generate_ontology(text, context)
        score = critic.evaluate_ontology(ontology, context, text)
        
        # Save ontology
        output_file = output_dir / f"{file.stem}_ontology.json"
        with open(output_file, 'w') as f:
            json.dump(ontology, f, indent=2, default=str)
        
        results.append({
            'file': str(file),
            'entities': len(ontology['entities']),
            'score': score.overall,
        })
        
        print(f"  {file}: {len(ontology['entities'])} entities, score={score.overall:.2f}")
    
    # Save summary
    with open(output_dir / "extraction_summary.json", 'w') as f:
        json.dump(results, f, indent=2)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## Flask REST API

Lightweight REST API using Flask.

```python
"""
flask_ontology_api.py - Flask REST API for ontology extraction
"""

from flask import Flask, request, jsonify
from flask_cors import CORS

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
)

app = Flask(__name__)
CORS(app)  # Enable CORS for browser access

generator = OntologyGenerator()
critic = OntologyCritic()


@app.route('/api/extract', methods=['POST'])
def extract():
    """Extract ontology from text."""
    
    data = request.get_json()
    
    if not data or 'text' not in data:
        return jsonify({'error': 'Missing text field'}), 400
    
    text = data['text']
    domain = data.get('domain', 'general')
    strategy = data.get('strategy', 'rule_based')
    
    try:
        context = OntologyGenerationContext(
            data_source="api_request",
            data_type=DataType.TEXT,
            domain=domain,
            extraction_strategy=ExtractionStrategy[strategy.upper()],
        )
        
        ontology = generator.generate_ontology(text, context)
        score = critic.evaluate_ontology(ontology, context, text)
        
        return jsonify({
            'entities': ontology['entities'],
            'relationships': ontology['relationships'],
            'score': {
                'overall': score.overall,
                'completeness': score.completeness,
                'consistency': score.consistency,
            },
            'metadata': {
                'text_length': len(text),
                'domain': domain,
                'strategy': strategy,
            }
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check."""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

## Command-Line Tool

Full-featured CLI tool for ontology extraction.

```python
"""
ontology_cli.py - Command-line tool for ontology extraction
"""

import click
import json
from pathlib import Path

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyMediator,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
    ExtractionConfig,
)


@click.group()
def cli():
    """GraphRAG Ontology Extraction CLI"""
    pass


@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), help='Output file (default: stdout)')
@click.option('--domain', '-d', default='general', help='Document domain')
@click.option('--strategy', '-s', type=click.Choice(['rule_based', 'llm_fallback', 'pure_llm']), 
              default='rule_based', help='Extraction strategy')
@click.option('--refine', is_flag=True, help='Run refinement cycle')
@click.option('--confidence', type=float, help='Confidence threshold')
def extract(input_file, output, domain, strategy, refine, confidence):
    """Extract ontology from a document."""
    
    # Read input
    text = Path(input_file).read_text()
    
    # Create generator
    config = ExtractionConfig()
    if confidence:
        config.confidence_threshold = confidence
    
    generator = OntologyGenerator(config=config)
    critic = OntologyCritic()
    
    # Create context
    context = OntologyGenerationContext(
        data_source=input_file,
        data_type=DataType.TEXT,
        domain=domain,
        extraction_strategy=ExtractionStrategy[strategy.upper()],
    )
    
    if refine:
        # Refinement cycle
        mediator = OntologyMediator(generator=generator, critic=critic)
        state = mediator.run_refinement_cycle(text, context)
        ontology = state['current_ontology']
        score = state['critic_scores'][-1]
        
        result = {
            'ontology': ontology,
            'score': {
                'overall': score.overall,
                'completeness': score.completeness,
                'consistency': score.consistency,
            },
            'refinement_rounds': state['current_round'],
        }
    else:
        # Single extraction
        ontology = generator.generate_ontology(text, context)
        score = critic.evaluate_ontology(ontology, context, text)
        
        result = {
            'ontology': ontology,
            'score': {
                'overall': score.overall,
                'completeness': score.completeness,
                'consistency': score.consistency,
            }
        }
    
    # Output
    if output:
        with open(output, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        click.echo(f"Ontology saved to {output}")
    else:
        click.echo(json.dumps(result, indent=2, default=str))


@cli.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--output-dir', '-o', type=click.Path(), required=True, help='Output directory')
@click.option('--pattern', '-p', default='*.txt', help='File pattern')
@click.option('--domain', '-d', default='general', help='Document domain')
@click.option('--workers', '-w', type=int, default=4, help='Parallel workers')
def batch(directory, output_dir, pattern, domain, workers):
    """Process multiple documents in batch."""
    
    from batch_processor import BatchProcessor
    
    processor = BatchProcessor(max_workers=workers)
    results = processor.process_directory(
        input_dir=Path(directory),
        output_dir=Path(output_dir),
        domain=domain,
        pattern=pattern,
    )
    
    click.echo(f"Processed {len(results)} documents")


@cli.command()
@click.argument('ontology_file', type=click.Path(exists=True))
@click.argument('source_file', type=click.Path(exists=True))
@click.option('--domain', '-d', default='general', help='Document domain')
def evaluate(ontology_file, source_file, domain):
    """Evaluate ontology quality."""
    
    # Load ontology
    with open(ontology_file) as f:
        ontology = json.load(f)
    
    # Load source text
    text = Path(source_file).read_text()
    
    # Create context
    context = OntologyGenerationContext(
        data_source=source_file,
        data_type=DataType.TEXT,
        domain=domain,
        extraction_strategy=ExtractionStrategy.RULE_BASED,
    )
    
    # Evaluate
    critic = OntologyCritic()
    score = critic.evaluate_ontology(ontology, context, text)
    
    click.echo(f"Ontology Quality Score:")
    click.echo(f"  Overall: {score.overall:.2f}")
    click.echo(f"  Completeness: {score.completeness:.2f}")
    click.echo(f"  Consistency: {score.consistency:.2f}")
    click.echo(f"  Clarity: {score.clarity:.2f}")
    click.echo(f"  Granularity: {score.granularity:.2f}")
    click.echo(f"  Relationship Coherence: {score.relationship_coherence:.2f}")
    click.echo(f"  Domain Alignment: {score.domain_alignment:.2f}")


if __name__ == '__main__':
    cli()
```

**Usage**:
```bash
# Extract from single file
python ontology_cli.py extract document.txt -o ontology.json -d legal

# Extract with refinement
python ontology_cli.py extract document.txt -o ontology.json --refine

# Batch processing
python ontology_cli.py batch ./documents -o ./ontologies -w 4

# Evaluate existing ontology
python ontology_cli.py evaluate ontology.json document.txt -d legal
```

## Jupyter Notebook Analysis

Interactive analysis and visualization in Jupyter notebooks.

```python
"""
Ontology Analysis Notebook
"""

# Cell 1: Setup
from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
)
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Initialize components
generator = OntologyGenerator()
critic = OntologyCritic()

# Cell 2: Extract ontology
sample_text = """
Alice is an employee of Acme Corporation. She reports to Bob, the manager.
Acme Corporation is based in New York. Alice completed her annual training
in March 2024.
"""

context = OntologyGenerationContext(
    data_source="sample",
    data_type=DataType.TEXT,
    domain="business",
    extraction_strategy=ExtractionStrategy.RULE_BASED,
)

ontology = generator.generate_ontology(sample_text, context)
score = critic.evaluate_ontology(ontology, context, sample_text)

print(f"Entities: {len(ontology['entities'])}")
print(f"Relationships: {len(ontology['relationships'])}")
print(f"Quality Score: {score.overall:.2f}")

# Cell 3: Visualize entities
entities_df = pd.DataFrame(ontology['entities'])
print(entities_df[['text', 'type', 'confidence']])

# Entity type distribution
entities_df['type'].value_counts().plot(kind='bar')
plt.title('Entity Type Distribution')
plt.xlabel('Entity Type')
plt.ylabel('Count')
plt.show()

# Cell 4: Visualize quality scores
score_data = {
    'Dimension': ['Completeness', 'Consistency', 'Clarity', 'Granularity', 
                  'Relationship Coherence', 'Domain Alignment'],
    'Score': [score.completeness, score.consistency, score.clarity, 
              score.granularity, score.relationship_coherence, score.domain_alignment]
}
score_df = pd.DataFrame(score_data)

plt.figure(figsize=(10, 6))
sns.barplot(data=score_df, x='Dimension', y='Score')
plt.title('Ontology Quality Dimensions')
plt.xticks(rotation=45)
plt.ylim(0, 1)
plt.show()

# Cell 5: Analyze relationships
relationships_df = pd.DataFrame(ontology['relationships'])
print(relationships_df[['source_id', 'target_id', 'type', 'confidence']])

# Relationship type distribution
relationships_df['type'].value_counts().plot(kind='pie', autopct='%1.1f%%')
plt.title('Relationship Type Distribution')
plt.ylabel('')
plt.show()

# Cell 6: Confidence distribution
plt.figure(figsize=(12, 5))

plt.subplot(1, 2, 1)
plt.hist(entities_df['confidence'], bins=20, edgecolor='black')
plt.title('Entity Confidence Distribution')
plt.xlabel('Confidence')
plt.ylabel('Frequency')

plt.subplot(1, 2, 2)
plt.hist(relationships_df['confidence'], bins=20, edgecolor='black')
plt.title('Relationship Confidence Distribution')
plt.xlabel('Confidence')
plt.ylabel('Frequency')

plt.tight_layout()
plt.show()
```

## Streaming Processing

For very large documents or real-time processing.

```python
"""
streaming_processor.py - Stream-based document processing
"""

from typing import Iterator, Dict
from pathlib import Path

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
    ExtractionConfig,
)


class StreamingProcessor:
    """Process documents in streaming mode for large files."""
    
    def __init__(self, chunk_size: int = 5000):
        self.chunk_size = chunk_size  # tokens
        self.generator = OntologyGenerator(
            config=ExtractionConfig(
                max_entities=50,  # Limit per chunk
                max_relationships=75,
            )
        )
    
    def process_file_streaming(
        self,
        file_path: Path,
        domain: str = "general",
    ) -> Iterator[Dict]:
        """
        Process file in streaming mode, yielding results as they're ready.
        
        Yields:
            Chunk results with entities and relationships
        """
        
        context = OntologyGenerationContext(
            data_source=str(file_path),
            data_type=DataType.TEXT,
            domain=domain,
            extraction_strategy=ExtractionStrategy.RULE_BASED,
        )
        
        # Read file in chunks
        with open(file_path, 'r') as f:
            buffer = ""
            chunk_id = 0
            
            for line in f:
                buffer += line
                token_count = len(buffer.split())
                
                if token_count >= self.chunk_size:
                    # Process chunk
                    ontology = self.generator.generate_ontology(buffer, context)
                    
                    yield {
                        'chunk_id': chunk_id,
                        'entities': ontology['entities'],
                        'relationships': ontology['relationships'],
                        'token_count': token_count,
                    }
                    
                    # Reset buffer (with overlap)
                    overlap = " ".join(buffer.split()[-100:])  # Keep last 100 tokens
                    buffer = overlap
                    chunk_id += 1
            
            # Process remaining buffer
            if buffer.strip():
                ontology = self.generator.generate_ontology(buffer, context)
                yield {
                    'chunk_id': chunk_id,
                    'entities': ontology['entities'],
                    'relationships': ontology['relationships'],
                    'token_count': len(buffer.split()),
                }


# Usage
if __name__ == "__main__":
    processor = StreamingProcessor(chunk_size=5000)
    
    for chunk_result in processor.process_file_streaming(Path("large_document.txt"), domain="legal"):
        print(f"Chunk {chunk_result['chunk_id']}: "
              f"{len(chunk_result['entities'])} entities, "
              f"{len(chunk_result['relationships'])} relationships")
        
        # Process or save chunk result immediately
        # This prevents memory buildup for very large files
```

## Multi-Domain Pipeline

Process documents from multiple domains in a unified pipeline.

```python
"""
multi_domain_pipeline.py - Pipeline for heterogeneous document collections
"""

from pathlib import Path
from typing import Dict, List
import json

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
    ExtractionConfig,
)


class MultiDomainPipeline:
    """Pipeline for processing documents from multiple domains."""
    
    DOMAIN_CONFIGS = {
        'legal': ExtractionConfig(
            confidence_threshold=0.7,
            max_entities=150,
            max_relationships=250,
        ),
        'medical': ExtractionConfig(
            confidence_threshold=0.8,
            max_entities=100,
            max_relationships=150,
        ),
        'business': ExtractionConfig(
            confidence_threshold=0.6,
            max_entities=120,
            max_relationships=200,
        ),
        'general': ExtractionConfig(
            confidence_threshold=0.5,
            max_entities=100,
            max_relationships=150,
        ),
    }
    
    def __init__(self):
        self.generators = {
            domain: OntologyGenerator(config=config)
            for domain, config in self.DOMAIN_CONFIGS.items()
        }
        self.critic = OntologyCritic()
    
    def process_document(
        self,
        text: str,
        domain: str,
        data_source: str,
    ) -> Dict:
        """Process a single document with domain-specific configuration."""
        
        if domain not in self.generators:
            domain = 'general'  # Fallback
        
        generator = self.generators[domain]
        
        context = OntologyGenerationContext(
            data_source=data_source,
            data_type=DataType.TEXT,
            domain=domain,
            extraction_strategy=ExtractionStrategy.RULE_BASED,
        )
        
        ontology = generator.generate_ontology(text, context)
        score = self.critic.evaluate_ontology(ontology, context, text)
        
        return {
            'ontology': ontology,
            'score': score,
            'domain': domain,
            'metadata': {
                'text_length': len(text),
                'entity_count': len(ontology['entities']),
                'relationship_count': len(ontology['relationships']),
            }
        }
    
    def process_collection(
        self,
        documents: List[Dict[str, str]],
        output_dir: Path,
    ) -> List[Dict]:
        """
        Process a collection of documents with mixed domains.
        
        Args:
            documents: List of {'text': str, 'domain': str, 'id': str}
            output_dir: Directory to save results
        
        Returns:
            List of processing results
        """
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        
        for doc in documents:
            result = self.process_document(
                text=doc['text'],
                domain=doc['domain'],
                data_source=doc['id'],
            )
            
            # Save individual result
            output_file = output_dir / f"{doc['id']}_ontology.json"
            with open(output_file, 'w') as f:
                json.dump(result['ontology'], f, indent=2, default=str)
            
            results.append({
                'document_id': doc['id'],
                'domain': doc['domain'],
                'score': result['score'].overall,
                'entities': result['metadata']['entity_count'],
                'relationships': result['metadata']['relationship_count'],
            })
        
        # Generate cross-domain analysis
        self._generate_cross_domain_analysis(results, output_dir)
        
        return results
    
    def _generate_cross_domain_analysis(self, results: List[Dict], output_dir: Path):
        """Generate analysis comparing performance across domains."""
        
        from collections import defaultdict
        
        by_domain = defaultdict(list)
        for r in results:
            by_domain[r['domain']].append(r)
        
        analysis = {}
        for domain, domain_results in by_domain.items():
            analysis[domain] = {
                'document_count': len(domain_results),
                'average_score': sum(r['score'] for r in domain_results) / len(domain_results),
                'average_entities': sum(r['entities'] for r in domain_results) / len(domain_results),
                'average_relationships': sum(r['relationships'] for r in domain_results) / len(domain_results),
            }
        
        with open(output_dir / "cross_domain_analysis.json", 'w') as f:
            json.dump(analysis, f, indent=2)


# Usage
if __name__ == "__main__":
    pipeline = MultiDomainPipeline()
    
    documents = [
        {'text': '...legal contract...', 'domain': 'legal', 'id': 'contract_001'},
        {'text': '...medical record...', 'domain': 'medical', 'id': 'record_001'},
        {'text': '...business report...', 'domain': 'business', 'id': 'report_001'},
    ]
    
    results = pipeline.process_collection(documents, output_dir=Path("./ontologies"))
```

## Semantic Entity Deduplication

Use embedding-based semantic similarity to merge duplicate entities with different surface forms.

```python
"""
semantic_dedup_example.py - Demonstrate semantic entity deduplication
"""

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
    ExtractionConfig,
)


# Example 1: Enable semantic dedup at initialization
def enable_semantic_dedup_example():
    """Enable semantic dedup when creating OntologyGenerator."""
    
    generator = OntologyGenerator(
        config=ExtractionConfig(
            confidence_threshold=0.6,
            max_entities=100,
            max_relationships=150,
        ),
        enable_semantic_dedup=True,  # Enable semantic deduplication
    )
    
    # Process text with many duplicate entities
    text = """
    Microsoft Corporation announced a partnership with OpenAI.
    The software giant, Microsoft, has been investing in AI.
    MS and Open AI are collaborating on GPT models.
    """
    
    context = OntologyGenerationContext(
        data_source="example",
        data_type=DataType.TEXT,
        domain="technology",
        extraction_strategy=ExtractionStrategy.RULE_BASED,
    )
    
    # Extract entities - duplicates are NOT merged yet
    result = generator.extract_entities(text, context)
    
    print(f"Entities before dedup: {len(result.entities)}")
    # May contain: "Microsoft", "Microsoft Corporation", "MS", "software giant"
    
    # Apply semantic deduplication
    deduplicated_result = result.apply_semantic_dedup(
        similarity_threshold=0.85,  # Entities with >85% similarity are merged
        batch_size=32,             # Process 32 entities at a time
    )
    
    print(f"Entities after dedup: {len(deduplicated_result.entities)}")
    # Should merge: "Microsoft" ← "Microsoft Corporation", "MS", "software giant"
    #               "OpenAI" ← "Open AI"
    
    # Relationships are automatically remapped to canonical entity IDs
    for rel in deduplicated_result.relationships:
        print(f"{rel['source']} -> {rel['target']} ({rel['type']})")


# Example 2: Post-processing deduplication
def post_processing_dedup_example():
    """Apply semantic dedup as a post-processing step."""
    
    # Generator without semantic dedup enabled
    generator = OntologyGenerator(
        config=ExtractionConfig(
            confidence_threshold=0.7,
            max_entities=200,
        ),
        enable_semantic_dedup=False,  # Disabled at init
    )
    
    texts = [
        "Apple Inc. released a new iPhone.",
        "The tech company Apple announced quarterly earnings.",
        "AAPL stock price increased after the iPhone launch.",
    ]
    
    all_entities = []
    all_relationships = []
    
    context = OntologyGenerationContext(
        data_source="news_corpus",
        data_type=DataType.TEXT,
        domain="business",
        extraction_strategy=ExtractionStrategy.RULE_BASED,
    )
    
    # Extract from multiple documents
    for text in texts:
        result = generator.extract_entities(text, context)
        all_entities.extend(result.entities)
        all_relationships.extend(result.relationships)
    
    # Combine into single result
    from ipfs_datasets_py.optimizers.graphrag.entity_extraction import EntityExtractionResult
    
    combined_result = EntityExtractionResult(
        entities=all_entities,
        relationships=all_relationships,
        confidence=0.7,
        metadata={"source_count": len(texts)},
    )
    
    print(f"Combined entities before dedup: {len(combined_result.entities)}")
    
    # Apply semantic dedup to merged results
    deduplicated = combined_result.apply_semantic_dedup(
        similarity_threshold=0.80,
        batch_size=64,
    )
    
    print(f"Combined entities after dedup: {len(deduplicated.entities)}")
    # Merges: "Apple Inc." ← "Apple", "AAPL", "tech company"


# Example 3: Graceful degradation
def graceful_degradation_example():
    """
    Semantic dedup gracefully degrades if sentence-transformers is unavailable.
    """
    
    # If sentence-transformers is not installed, this will log a warning
    # and semantic dedup operations will be no-ops
    generator = OntologyGenerator(
        enable_semantic_dedup=True,  # Requested, but may not be available
    )
    
    text = "Example text with duplicate entities."
    context = OntologyGenerationContext(
        data_source="test",
        data_type=DataType.TEXT,
        domain="general",
        extraction_strategy=ExtractionStrategy.RULE_BASED,
    )
    
    result = generator.extract_entities(text, context)
    
    # If dependencies are missing, this returns the original result unchanged
    deduplicated = result.apply_semantic_dedup()
    
    # Your code continues to work without crashing
    print(f"Entities: {len(deduplicated.entities)}")


# Example 4: Integration with refinement cycle
def refinement_with_dedup_example():
    """Use semantic dedup in adversarial refinement workflow."""
    
    from ipfs_datasets_py.optimizers.graphrag import (
        OntologyMediator,
        OntologyCritic,
    )
    
    generator = OntologyGenerator(
        config=ExtractionConfig(confidence_threshold=0.65),
        enable_semantic_dedup=True,
    )
    
    critic = OntologyCritic()
    mediator = OntologyMediator(
        generator=generator,
        critic=critic,
        max_rounds=5,
    )
    
    text = """
    Amazon Web Services (AWS) provides cloud infrastructure.
    Amazon's cloud platform supports machine learning workloads.
    The e-commerce giant Amazon also offers AWS certification programs.
    """
    
    context = OntologyGenerationContext(
        data_source="cloud_docs",
        data_type=DataType.TEXT,
        domain="technology",
        extraction_strategy=ExtractionStrategy.LLM_FALLBACK,
    )
    
    # Run refinement cycle
    final_state = mediator.run_refinement_cycle(text, context)
    ontology = final_state['current_ontology']
    
    # Refinement may create duplicate entities across rounds
    # Apply semantic dedup to final ontology
    from ipfs_datasets_py.optimizers.graphrag.entity_extraction import EntityExtractionResult
    
    result = EntityExtractionResult(
        entities=ontology['entities'],
        relationships=ontology['relationships'],
        confidence=0.8,
        metadata={'refinement_rounds': final_state['current_round']},
    )
    
    deduplicated = result.apply_semantic_dedup(similarity_threshold=0.82)
    
    # Use deduplicated ontology
    final_ontology = {
        'entities': deduplicated.entities,
        'relationships': deduplicated.relationships,
        'metadata': deduplicated.metadata,
    }
    
    print(f"Final ontology: {len(final_ontology['entities'])} entities")


if __name__ == "__main__":
    print("=== Example 1: Enable at initialization ===")
    enable_semantic_dedup_example()
    
    print("\n=== Example 2: Post-processing dedup ===")
    post_processing_dedup_example()
    
    print("\n=== Example 3: Graceful degradation ===")
    graceful_degradation_example()
    
    print("\n=== Example 4: Refinement with dedup ===")
    refinement_with_dedup_example()
```

**Key Points**:

1. **Feature Flag**: Enable via `enable_semantic_dedup=True` parameter on `OntologyGenerator`
2. **Post-processing**: Call `result.apply_semantic_dedup()` on `EntityExtractionResult` objects
3. **Graceful Degradation**: If `sentence-transformers` is unavailable, dedup operations are no-ops
4. **Relationship Remapping**: When entities are merged, all relationships automatically point to canonical IDs
5. **Self-reference Removal**: Relationships where source == target after merging are automatically removed
6. **Tunable Threshold**: Adjust `similarity_threshold` (0.0-1.0) based on domain and precision needs

**Configuration Parameters**:

```python
result.apply_semantic_dedup(
    similarity_threshold=0.85,  # Cosine similarity threshold for merging (default: 0.85)
    batch_size=32,             # Entities processed per batch (default: 32)
)
```

**Dependencies**:

```bash
# Required for semantic deduplication
pip install sentence-transformers
```

**When to Use Semantic Dedup**:

- ✅ Multi-document processing with entity name variations
- ✅ Cross-lingual entity extraction (different translations)
- ✅ Adversarial refinement cycles (duplicates across rounds)
- ✅ Entity linking from noisy/informal text (social media, transcripts)
- ⚠️  High-precision legal documents (prefer exact matching to avoid false merges)
- ⚠️  Small ontologies (<50 entities) where dedup overhead exceeds benefit

**Performance**:

- **Embedding Model**: `all-MiniLM-L6-v2` (90MB, 384-dim embeddings)
- **Throughput**: ~1000 entities/second on CPU, ~5000 entities/second on GPU
- **Memory**: ~4MB per 1000 entities for embedding cache

## Additional Resources

- **[PERFORMANCE_TUNING_GUIDE.md](PERFORMANCE_TUNING_GUIDE.md)** - Optimization strategies
- **[TROUBLESHOOTING_GUIDE.md](TROUBLESHOOTING_GUIDE.md)** - Solutions to common issues
- **[README.md](../ipfs_datasets_py/optimizers/README.md)** - Main documentation

## Prometheus Metrics Scrape

Enable metrics and scrape the REST API for Prometheus-compatible output:

```bash
export ENABLE_PROMETHEUS=true
curl http://localhost:8000/metrics
```

## Version History

- **v1.0** (2026-02-23): Initial integration examples with 8 real-world scenarios

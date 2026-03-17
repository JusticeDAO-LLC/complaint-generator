"""Benchmark for P2 sentence-window limiting optimization.

This benchmark measures the performance impact of sentence-window limiting on 
relationship inference across different document types and sizes.

Usage:
    pytest benchmarks/bench_sentence_window_scaling.py -v --benchmark-group-by=func
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
    ExtractionConfig,
    DataType,
)


@pytest.fixture
def generator():
    """Create OntologyGenerator instance."""
    return OntologyGenerator()


@pytest.fixture
def legal_text_small():
    """Small legal document (500 chars, ~3 sentences)."""
    return (
        "Alice entered into a contract with Bob on January 1, 2024. "
        "The contract obligates Alice to pay Bob $100 per month. "
        "Bob agrees to provide consulting services for Alice."
    )


@pytest.fixture
def legal_text_medium():
    """Medium legal document (~1500 chars, ~12 sentences)."""
    return (
        "AGREEMENT: This agreement is entered into as of January 1, 2024, "
        "by and between Alice, Inc. (Purchaser) and Bob Corp. (Vendor). "
        "Whereas, Purchaser desires to purchase consulting services from Vendor; "
        "Whereas, Vendor has agreed to provide such services; "
        "NOW, THEREFORE, in consideration of the mutual covenants herein: "
        "1. SERVICES. Vendor shall provide consulting services to Purchaser as detailed in Schedule A. "
        "2. TERM. This Agreement shall commence on January 1, 2024 and continue for one year. "
        "3. PAYMENT. Purchaser shall pay Vendor $50,000 annually in twelve monthly installments. "
        "4. CONFIDENTIALITY. Both parties agree to maintain confidentiality of all proprietary information. "
        "5. LIABILITY. Neither party shall be liable for indirect or consequential damages. "
        "6. TERMINATION. Either party may terminate this Agreement with sixty days written notice. "
        "7. DISPUTE RESOLUTION. Disputes shall be resolved through binding arbitration in New York. "
        "IN WITNESS WHEREOF, the parties execute this Agreement as of the date first written above."
    )


@pytest.fixture
def technical_text_small():
    """Small technical document (400 chars, ~3 sentences)."""
    return (
        "The REST API accepts JSON payloads and returns HTTP 200 on success. "
        "Clients should implement exponential backoff for rate-limited responses. "
        "The SDK provides convenience wrappers for common operations."
    )


@pytest.fixture
def technical_text_medium():
    """Medium technical document (~1200 chars, ~10 sentences)."""
    return (
        "The GraphQL endpoint is accessible at https://api.example.com/graphql. "
        "Authentication requires a bearer token in the Authorization header. "
        "The schema supports queries, mutations, and subscriptions. "
        "Queries return paginated results with cursor-based navigation. "
        "The system rate-limits API calls to 1000 requests per minute per client. "
        "Mutations are atomic and roll back on any validation error. "
        "Subscriptions use WebSocket connections for real-time updates. "
        "All payloads are validated against a strict JSON Schema specification. "
        "The API versions are specified in the X-API-Version header. "
        "Clients should cache responses for sixty seconds to minimize latency."
    )


@pytest.fixture
def financial_text_small():
    """Small financial document (450 chars, ~3 sentences)."""
    return (
        "The portfolio contains 1000 shares of ACME Corp valued at $50,000. "
        "Interest accrues monthly at 5% and compounds annually. "
        "The account manager charges a 1% annual management fee."
    )


@pytest.fixture
def financial_text_medium():
    """Medium financial document (~1400 chars, ~12 sentences)."""
    return (
        "Portfolio Summary: Total assets under management are $500,000 in USD. "
        "The investment strategy is 60% equities and 40% fixed income. "
        "Current holdings include 100 shares of TECH Inc. worth $25,000 each. "
        "The fixed income portion consists of US Treasury bonds yielding 4% annually. "
        "Year-to-date performance shows a 12% return on equity positions. "
        "Dividend income of $15,000 was reinvested in the portfolio last month. "
        "The account carries a margin balance of $50,000 at 8% interest. "
        "Currency holdings include EUR 10,000 and GBP 5,000 for hedging. "
        "Annual management fees are deducted quarterly at 0.75% of assets. "
        "Rebalancing occurs semi-annually to maintain target allocations. "
        "Tax-loss harvesting generated $8,000 in deductions this year. "
        "The custodian provides monthly statements and annual 1099-B reporting."
    )


class TestSentenceWindowScaling:
    """Benchmark suite for sentence-window limiting optimization."""

    def test_legal_small_no_window(self, benchmark, generator, legal_text_small):
        """Baseline: Legal text without sentence-window limiting."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="legal",
            config=ExtractionConfig(
                sentence_window=0,  # No limiting
                enable_parallel_inference=False,  # Serial for fair comparison
            ),
        )
        
        def extract():
            entities = generator.extract_entities(legal_text_small, context)
            return len(entities.entities)
        
        result = benchmark(extract)
        assert result >= 0

    def test_legal_small_window_1(self, benchmark, generator, legal_text_small):
        """Legal text with sentence_window=1."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="legal",
            config=ExtractionConfig(
                sentence_window=1,  # Adjacent sentences only
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(legal_text_small, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_legal_small_window_2(self, benchmark, generator, legal_text_small):
        """Legal text with sentence_window=2."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="legal",
            config=ExtractionConfig(
                sentence_window=2,  # Up to 2 sentences away
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(legal_text_small, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_legal_medium_no_window(self, benchmark, generator, legal_text_medium):
        """Baseline: Larger legal text without sentence-window limiting."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="legal",
            config=ExtractionConfig(
                sentence_window=0,  # No limiting
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(legal_text_medium, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_legal_medium_window_1(self, benchmark, generator, legal_text_medium):
        """Larger legal text with sentence_window=1."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="legal",
            config=ExtractionConfig(
                sentence_window=1,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(legal_text_medium, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_legal_medium_window_2(self, benchmark, generator, legal_text_medium):
        """Larger legal text with sentence_window=2."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="legal",
            config=ExtractionConfig(
                sentence_window=2,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(legal_text_medium, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_technical_small_no_window(self, benchmark, generator, technical_text_small):
        """Baseline: Technical text without sentence-window limiting."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="technical",
            config=ExtractionConfig(
                sentence_window=0,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(technical_text_small, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_technical_small_window_1(self, benchmark, generator, technical_text_small):
        """Technical text with sentence_window=1."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="technical",
            config=ExtractionConfig(
                sentence_window=1,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(technical_text_small, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_technical_medium_no_window(self, benchmark, generator, technical_text_medium):
        """Baseline: Larger technical text without sentence-window limiting."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="technical",
            config=ExtractionConfig(
                sentence_window=0,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(technical_text_medium, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_technical_medium_window_2(self, benchmark, generator, technical_text_medium):
        """Larger technical text with sentence_window=2."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="technical",
            config=ExtractionConfig(
                sentence_window=2,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(technical_text_medium, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_financial_small_no_window(self, benchmark, generator, financial_text_small):
        """Baseline: Financial text without sentence-window limiting."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="financial",
            config=ExtractionConfig(
                sentence_window=0,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(financial_text_small, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_financial_small_window_1(self, benchmark, generator, financial_text_small):
        """Financial text with sentence_window=1."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="financial",
            config=ExtractionConfig(
                sentence_window=1,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(financial_text_small, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_financial_medium_no_window(self, benchmark, generator, financial_text_medium):
        """Baseline: Larger financial text without sentence-window limiting."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="financial",
            config=ExtractionConfig(
                sentence_window=0,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(financial_text_medium, context)
            return len(entities.entities)
        
        benchmark(extract)

    def test_financial_medium_window_2(self, benchmark, generator, financial_text_medium):
        """Larger financial text with sentence_window=2."""
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="financial",
            config=ExtractionConfig(
                sentence_window=2,
                enable_parallel_inference=False,
            ),
        )
        
        def extract():
            entities = generator.extract_entities(financial_text_medium, context)
            return len(entities.entities)
        
        benchmark(extract)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-group-by=func"])

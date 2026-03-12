# Complaint Analysis Examples

Comprehensive examples showing how to use and extend the complaint_analysis module.

## Built-in Complaint Types

The module now includes 12 comprehensive taxonomies covering major practice areas:

- **Housing** - Fair housing, landlord-tenant, Section 8, reasonable accommodation
- **Employment** - Title VII, EEOC, workplace discrimination, wrongful termination
- **Civil Rights** - Police misconduct, voting rights, constitutional violations
- **Consumer Protection** - Fraud, deceptive practices, FTC violations
- **Healthcare** - Medical malpractice, HIPAA, patient rights, EMTALA
- **Free Speech/Censorship** - First Amendment, content moderation, prior restraint
- **Immigration** - Visa, asylum, deportation, USCIS, ICE proceedings
- **Family Law** - Divorce, custody, child support, domestic violence
- **Criminal Defense** - Miranda rights, illegal search, due process, habeas corpus
- **Tax Law** - IRS disputes, tax court, innocent spouse relief, offer in compromise
- **Intellectual Property** - Patents, trademarks, copyrights, trade secrets
- **Environmental Law** - EPA violations, Clean Air/Water Act, CERCLA, pollution

For a comprehensive demonstration, run:
```bash
python3 examples/complaint_analysis_taxonomies_demo.py
```

## Table of Contents

0. [Built-in Complaint Types](#built-in-complaint-types)
1. [Basic Usage](#basic-usage)
2. [Extending with New Complaint Types](#extending-with-new-complaint-types)
3. [Custom Risk Scoring](#custom-risk-scoring)
4. [Integration with ipfs_datasets_py](#integration-with-ipfs_datasets_py)
5. [Batch Processing](#batch-processing)

---

## Basic Usage

### Simple Analysis

```python
from complaint_analysis import ComplaintAnalyzer

# Analyze a complaint
text = """
I am filing a complaint regarding fair housing discrimination. My landlord refused 
to provide a reasonable accommodation for my disability. This violates the Fair 
Housing Act and constitutes discrimination based on a protected class.
"""

analyzer = ComplaintAnalyzer(complaint_type='housing')
result = analyzer.analyze(text)

print(f"Risk Level: {result['risk_level']}")
print(f"Risk Score: {result['risk_score']}/3")
print(f"Categories: {result['categories']}")
print(f"Legal Provisions: {result['legal_provisions']['provision_count']}")
print(f"Recommendations:")
for rec in result['recommendations']:
    print(f"  - {rec}")
```

### Component-by-Component

```python
from complaint_analysis import (
    LegalPatternExtractor,
    ComplaintRiskScorer,
    get_keywords
)

text = "Employment discrimination complaint regarding Title VII violation..."

# 1. Extract legal provisions
extractor = LegalPatternExtractor()
provisions = extractor.extract_provisions(text)
print(f"Found {len(provisions['provisions'])} legal provisions")

# 2. Calculate risk
scorer = ComplaintRiskScorer()
risk = scorer.calculate_risk(text, provisions['provisions'])
print(f"Risk: {risk['level']} ({risk['score']})")

# 3. Get relevant keywords
employment_keywords = get_keywords('complaint', complaint_type='employment')
print(f"Employment keywords: {len(employment_keywords)} terms")
```

---

## Extending with New Complaint Types

### Example 1: Environmental Complaints

```python
from complaint_analysis import (
    register_keywords,
    register_legal_terms,
    ComplaintAnalyzer
)

# Step 1: Register keywords
register_keywords('complaint', [
    'pollution', 'contamination', 'toxic waste', 'environmental hazard',
    'clean air act', 'clean water act', 'epa', 'superfund',
    'endangered species', 'wetlands', 'emissions',
], complaint_type='environmental')

# Step 2: Register legal patterns
register_legal_terms('environmental', [
    r'\b(clean air act)\b',
    r'\b(clean water act)\b',
    r'\b(cercla|superfund)\b',
    r'\b(epa|environmental protection agency)\b',
    r'\b(national environmental policy act|nepa)\b',
    r'\b(endangered species act)\b',
])

# Step 3: Use it
text = """
The factory has been releasing toxic emissions in violation of the Clean Air Act.
The EPA was notified but failed to act. This environmental hazard affects the
entire community and requires immediate remediation.
"""

analyzer = ComplaintAnalyzer(complaint_type='environmental')
result = analyzer.analyze(text)

print(f"Environmental Complaint Analysis:")
print(f"  Risk: {result['risk_level']}")
print(f"  Provisions found: {result['legal_provisions']['provision_count']}")
print(f"  Categories: {result['categories']}")
```

### Example 2: Immigration Complaints

```python
from complaint_analysis import register_keywords, register_legal_terms

# Register immigration-specific keywords
register_keywords('complaint', [
    'visa denial', 'deportation', 'asylum', 'refugee',
    'immigration detention', 'uscis', 'ice', 'cbp',
    'naturalization', 'green card', 'work permit',
    'family separation', 'due process',
], complaint_type='immigration')

register_legal_terms('immigration', [
    r'\b(ina|immigration and nationality act)\b',
    r'\b(uscis|ice|cbp)\b',
    r'\b(asylum|refugee)\b',
    r'\b(deportation|removal)\b',
    r'\b(visa|green card)\b',
])

# Now analyze immigration complaints
from complaint_analysis import ComplaintAnalyzer

analyzer = ComplaintAnalyzer(complaint_type='immigration')
text = "USCIS denied my asylum application without proper due process..."
result = analyzer.analyze(text)
```

### Example 3: Education Complaints

```python
from complaint_analysis import register_keywords, register_legal_terms

register_keywords('complaint', [
    'title ix', 'sexual harassment', 'education discrimination',
    'special education', 'idea', 'iep', '504 plan',
    'school suspension', 'expulsion', 'school discipline',
    'bullying', 'school safety',
], complaint_type='education')

register_legal_terms('education', [
    r'\b(title ix)\b',
    r'\b(idea|individuals with disabilities education act)\b',
    r'\b(iep|individualized education program)\b',
    r'\b(504 plan)\b',
    r'\b(ferpa|family educational rights)\b',
])
```

---

## Custom Risk Scoring

### Example: Multi-Level Risk Scorer

```python
from complaint_analysis.base import BaseRiskScorer

class DetailedRiskScorer(BaseRiskScorer):
    """
    Risk scorer with 5 levels instead of 4.
    """
    
    def __init__(self):
        self.risk_levels = ['minimal', 'low', 'medium', 'high', 'critical']
    
    def calculate_risk(self, text, legal_provisions=None, **kwargs):
        from complaint_analysis import get_keywords
        
        # Get keywords
        complaint_kw = get_keywords('complaint')
        binding_kw = get_keywords('binding')
        high_severity = get_keywords('severity_high')
        
        # Count matches
        complaint_count = sum(1 for kw in complaint_kw if kw.lower() in text.lower())
        binding_count = sum(1 for kw in binding_kw if kw.lower() in text.lower())
        severity_count = sum(1 for kw in high_severity if kw.lower() in text.lower())
        
        provision_count = len(legal_provisions) if legal_provisions else 0
        
        # Determine score (0-4)
        score = 0
        factors = []
        
        if severity_count > 2 and binding_count > 2 and provision_count > 5:
            score = 4  # Critical
            factors.append('Multiple severe violations with strong legal basis')
        elif severity_count > 0 and provision_count > 3:
            score = 3  # High
            factors.append('Severe legal issues identified')
        elif complaint_count > 3 and provision_count > 2:
            score = 2  # Medium
            factors.append('Multiple complaint indicators with legal basis')
        elif complaint_count > 0 or provision_count > 0:
            score = 1  # Low
            factors.append('Potential legal issues')
        
        return {
            'score': score,
            'level': self.risk_levels[score],
            'factors': factors,
            'complaint_keywords': complaint_count,
            'binding_keywords': binding_count,
            'legal_provisions': provision_count,
            'recommendations': self._generate_recs(score)
        }
    
    def get_risk_levels(self):
        return self.risk_levels
    
    def is_actionable(self, text, threshold=0.5):
        result = self.calculate_risk(text)
        normalized = result['score'] / 4.0  # 0-4 scale
        return normalized >= threshold
    
    def _generate_recs(self, score):
        if score == 4:
            return ['URGENT: Immediate legal action required', 
                    'Contact attorney immediately']
        elif score == 3:
            return ['High priority legal consultation needed',
                    'Gather all evidence']
        elif score == 2:
            return ['Consider legal consultation',
                    'Document situation carefully']
        elif score == 1:
            return ['Monitor situation', 'Keep records']
        else:
            return ['No immediate action needed']

# Usage
scorer = DetailedRiskScorer()
result = scorer.calculate_risk(complaint_text)
print(f"Risk: {result['level']} ({result['score']}/4)")
```

### Example: Domain-Specific Risk Scorer

```python
from complaint_analysis.base import BaseRiskScorer

class HousingRiskScorer(BaseRiskScorer):
    """Specialized risk scorer for housing complaints."""
    
    def __init__(self):
        self.risk_levels = ['minimal', 'low', 'medium', 'high']
        
        # Housing-specific risk factors
        self.critical_terms = [
            'unlawful eviction', 'retaliatory eviction',
            'habitability', 'unsafe conditions',
            'section 8 discrimination'
        ]
    
    def calculate_risk(self, text, legal_provisions=None, **kwargs):
        text_lower = text.lower()
        score = 0
        factors = []
        
        # Check for critical housing terms
        critical_count = sum(1 for term in self.critical_terms 
                            if term in text_lower)
        
        if critical_count > 0:
            score = 3
            factors.append(f'Critical housing issue: {critical_count} urgent terms')
        
        # Check for Fair Housing Act references
        if 'fair housing act' in text_lower or 'fha' in text_lower:
            score = max(score, 2)
            factors.append('Fair Housing Act referenced')
        
        # Check for discrimination claims
        if 'discrimination' in text_lower:
            score = max(score, 2)
            factors.append('Discrimination alleged')
        
        provision_count = len(legal_provisions) if legal_provisions else 0
        if provision_count > 3:
            score = max(score, 2)
            factors.append(f'{provision_count} legal provisions cited')
        
        return {
            'score': score,
            'level': self.risk_levels[score],
            'factors': factors,
            'critical_terms_found': critical_count,
            'recommendations': self._housing_recommendations(score)
        }
    
    def get_risk_levels(self):
        return self.risk_levels
    
    def is_actionable(self, text, threshold=0.5):
        result = self.calculate_risk(text)
        return result['score'] / 3.0 >= threshold
    
    def _housing_recommendations(self, score):
        if score == 3:
            return [
                'Contact housing attorney immediately',
                'Document all communications with landlord',
                'File complaint with HUD if discrimination',
                'Consider emergency injunction if eviction threat'
            ]
        elif score == 2:
            return [
                'Consult with tenant rights organization',
                'Review lease agreement carefully',
                'Gather evidence (photos, communications)',
                'Research local tenant protection laws'
            ]
        else:
            return ['Monitor situation', 'Know your tenant rights']
```

---

## Integration with ipfs_datasets_py

### Complete Evidence Pipeline

```python
from integrations.ipfs_datasets.documents import parse_document_file
from integrations.ipfs_datasets.search import search_brave_web
from complaint_analysis import ComplaintAnalyzer, register_consumer_complaint

def process_complaint_with_evidence(pdf_path, search_keywords):
    """
    Complete workflow: PDF processing + web evidence + legal analysis.
    """
    # Step 1: Parse the document through complaint-generator's adapter layer
    document_parse = parse_document_file(pdf_path)
    complaint_text = document_parse.get('text', '')
    
    # Step 2: Analyze complaint with complaint_analysis
    register_consumer_complaint()  # If consumer complaint
    analyzer = ComplaintAnalyzer(complaint_type='consumer')
    analysis = analyzer.analyze(complaint_text)
    
    # Step 3: Search for evidence through the normalized web-search adapter
    if analysis['risk_score'] >= 2:  # Medium or high risk
        query = f"site:gov {' OR '.join(search_keywords)}"
        evidence = search_brave_web(query, max_results=20)
    else:
        evidence = []
    
    return {
        'complaint_analysis': analysis,
        'pdf_processing': {
            'status': document_parse.get('status'),
            'text_length': len(complaint_text),
            'chunk_count': document_parse.get('summary', {}).get('chunk_count', 0),
            'provider': document_parse.get('provider')
        },
        'evidence_sources': len(evidence),
        'actionable': analysis['risk_score'] >= 2
    }

# Usage
result = process_complaint_with_evidence('complaint.pdf', ['consumer fraud', 'ftc'])
print(f"Analysis complete: Risk={result['complaint_analysis']['risk_level']}")
```

---

## Batch Processing

### Process Multiple Complaints

```python
from complaint_analysis import ComplaintAnalyzer
import asyncio

async def batch_analyze_complaints(complaints):
    """Analyze multiple complaints efficiently."""
    analyzer = ComplaintAnalyzer()
    results = []
    
    for idx, complaint_data in enumerate(complaints):
        try:
            result = analyzer.analyze(
                complaint_data['text'],
                metadata={'id': complaint_data['id']}
            )
            results.append({
                'id': complaint_data['id'],
                'risk_level': result['risk_level'],
                'categories': result['categories'],
                'actionable': result['risk_score'] >= 2
            })
            print(f"Processed {idx+1}/{len(complaints)}")
        except Exception as e:
            print(f"Error processing {complaint_data['id']}: {e}")
            results.append({'id': complaint_data['id'], 'error': str(e)})
    
    return results

# Usage
complaints = [
    {'id': 1, 'text': 'Housing discrimination complaint...'},
    {'id': 2, 'text': 'Employment complaint...'},
    {'id': 3, 'text': 'Consumer fraud complaint...'},
]

results = asyncio.run(batch_analyze_complaints(complaints))

# Summary
high_risk = [r for r in results if r.get('risk_level') == 'high']
print(f"High risk complaints: {len(high_risk)}")
```

---

## Advanced: Custom Complete Workflow

```python
from complaint_analysis import (
    LegalPatternExtractor,
    KeywordRegistry,
    BaseRiskScorer,
    register_keywords
)

class CustomComplaintSystem:
    """
    Custom complaint analysis system with domain-specific logic.
    """
    
    def __init__(self, domain='general'):
        self.domain = domain
        self.extractor = LegalPatternExtractor()
        self.keyword_registry = KeywordRegistry()
        
        # Register domain-specific keywords
        if domain == 'environmental':
            register_keywords('complaint', [
                'pollution', 'contamination', 'hazardous waste'
            ], complaint_type='environmental')
    
    def analyze(self, text):
        """Complete analysis with custom logic."""
        # Extract legal info
        provisions = self.extractor.extract_provisions(text)
        citations = self.extractor.extract_citations(text)
        
        # Custom risk calculation
        risk = self._custom_risk_calc(text, provisions)
        
        # Custom recommendations
        recommendations = self._custom_recommendations(risk, provisions)
        
        return {
            'provisions': provisions,
            'citations': citations,
            'risk': risk,
            'recommendations': recommendations,
            'domain': self.domain
        }
    
    def _custom_risk_calc(self, text, provisions):
        """Domain-specific risk calculation."""
        score = 0
        if len(provisions['provisions']) > 5:
            score += 2
        if 'violation' in text.lower():
            score += 1
        return {'score': score, 'level': 'high' if score >= 2 else 'low'}
    
    def _custom_recommendations(self, risk, provisions):
        """Generate domain-specific recommendations."""
        if risk['level'] == 'high':
            return ['Immediate action required', 'Contact specialist attorney']
        else:
            return ['Monitor situation', 'Document all incidents']

# Usage
system = CustomComplaintSystem(domain='environmental')
result = system.analyze(environmental_complaint_text)
```

---

## Testing Custom Extensions

```python
def test_custom_complaint_type():
    """Test adding a new complaint type."""
    from complaint_analysis import (
        register_keywords,
        get_keywords,
        ComplaintAnalyzer
    )
    
    # Register new type
    register_keywords('complaint', [
        'cryptocurrency', 'blockchain', 'digital asset'
    ], complaint_type='crypto')
    
    # Verify registration
    crypto_keywords = get_keywords('complaint', complaint_type='crypto')
    assert 'cryptocurrency' in crypto_keywords
    print("✓ Keywords registered")
    
    # Use with analyzer
    analyzer = ComplaintAnalyzer(complaint_type='crypto')
    text = "Cryptocurrency fraud involving blockchain technology..."
    result = analyzer.analyze(text)
    assert len(result['keywords_found']) > 0
    print("✓ Analyzer works with new type")
    
    print("✅ All tests passed!")

test_custom_complaint_type()
```

---

For more information, see the main [README.md](README.md).

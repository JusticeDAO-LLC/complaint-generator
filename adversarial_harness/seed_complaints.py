"""
Seed Complaints Library

Templates and generators for seed complaints across different types.
Now uses complaint_analysis.SeedGenerator for data-driven seed generation.
"""

import logging
from typing import Dict, Any, List

from complaint_analysis import SeedGenerator as AnalysisSeedGenerator

logger = logging.getLogger(__name__)


# Re-export the dataclass from complaint_analysis
from complaint_analysis.seed_generator import SeedComplaintTemplate as ComplaintTemplate


class SeedComplaintLibrary:
    """
    Library of seed complaints for testing.
    
    Now uses complaint_analysis.SeedGenerator to automatically generate
    templates from registered complaint types.
    """
    
    def __init__(self):
        """Initialize the seed complaint library."""
        # Use the complaint_analysis seed generator
        self._generator = AnalysisSeedGenerator()
        self.templates = self._generator.templates
        logger.info(f"Initialized with {len(self.templates)} templates from complaint_analysis")
    
    def register_template(self, template: ComplaintTemplate):
        """
        Register a new template.
        
        Args:
            template: Template to register
        """
        self.templates[template.id] = template
        logger.debug(f"Registered template: {template.id}")
    
    def get_template(self, template_id: str) -> ComplaintTemplate:
        """
        Get a template by ID.
        
        Args:
            template_id: Template identifier
            
        Returns:
            Template object
        """
        return self._generator.get_template(template_id)
    
    def list_templates(self, category: str = None) -> List[ComplaintTemplate]:
        """
        List available templates.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of templates
        """
        return self._generator.list_templates(category=category)
    
    def get_seed_complaints(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get a set of pre-defined seed complaints.
        
        Args:
            count: Number of seeds to return
            
        Returns:
            List of seed complaint data
        """
        seeds = []
        
        # Get templates from different categories
        categories = ['employment', 'housing', 'consumer', 'civil_rights', 'healthcare']
        templates_per_category = max(1, count // len(categories))
        
        for category in categories:
            category_templates = self._generator.list_templates(category=category)
            if not category_templates:
                continue
            
            # Take first few templates from this category
            for template in category_templates[:templates_per_category]:
                # Create example values based on template type
                values = self._get_example_values(template)
                try:
                    seed = template.instantiate(values)
                    seeds.append(seed)
                    if len(seeds) >= count:
                        break
                except ValueError as e:
                    logger.warning(f"Could not instantiate template {template.id}: {e}")
            
            if len(seeds) >= count:
                break
        
        return seeds[:count]
    
    def _get_example_values(self, template: ComplaintTemplate) -> Dict[str, Any]:
        """
        Generate example values for a template.
        
        Args:
            template: Template to generate values for
            
        Returns:
            Dictionary of example values
        """
        values = {}
        
        # Type-specific examples
        if template.type in ['employment_discrimination', 'wrongful_termination']:
            values.update({
                'employer_name': 'Acme Corporation',
                'position': 'Senior Engineer',
                'protected_class': 'race',
                'discriminatory_action': 'passed over for promotion',
                'date_of_incident': '2024-01-15',
                'termination_date': '2024-01-15',
                'termination_reason': 'alleged performance issues',
                'years_employed': 5
            })
        elif template.type in ['housing_discrimination', 'unlawful_eviction']:
            values.update({
                'landlord_name': 'Property Management LLC',
                'property_address': '123 Main St',
                'protected_class': 'familial status',
                'discriminatory_action': 'refused rental application',
                'date_of_incident': '2024-03-01',
                'eviction_reason': 'alleged lease violation',
                'notice_date': '2024-03-01'
            })
        elif template.type == 'consumer_fraud':
            values.update({
                'business_name': 'QuickFix Services',
                'product_or_service': 'home repair',
                'fraud_type': 'misrepresentation of work needed',
                'amount_lost': '$5000',
                'date_of_purchase': '2024-02-15'
            })
        elif template.type == 'civil_rights_violation':
            values.update({
                'violating_party': 'City Police Department',
                'type_of_violation': 'excessive force',
                'protected_right': 'freedom from unreasonable seizure',
                'date_of_incident': '2024-01-20'
            })
        elif template.type == 'medical_malpractice':
            values.update({
                'healthcare_provider': 'Dr. Smith',
                'facility_name': 'General Hospital',
                'type_of_negligence': 'misdiagnosis',
                'date_of_incident': '2024-02-10',
                'injuries_sustained': 'delayed treatment resulting in complications'
            })
        else:
            # Generic values for unknown types
            values.update({
                'party_name': 'Defendant Party',
                'issue_description': 'Detailed description of the legal issue',
                'date_of_incident': '2024-01-01'
            })
        
        return values

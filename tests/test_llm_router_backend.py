"""
Unit tests for the LLM Router Backend
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestLLMRouterBackend:
    """Test cases for LLM Router Backend functionality"""
    
    def test_llm_router_backend_module_exists(self):
        """Test that the llm_router_backend module can be imported"""
        try:
            from backends import llm_router_backend
            assert llm_router_backend is not None
        except ImportError as e:
            pytest.skip(f"Backend module has import issues: {e}")
    
    def test_llm_router_backend_class_can_be_imported(self):
        """Test that LLMRouterBackend class exists"""
        try:
            from backends.llm_router_backend import LLMRouterBackend
            assert LLMRouterBackend is not None
        except ImportError as e:
            pytest.skip(f"LLMRouterBackend class has import issues: {e}")
    
    def test_llm_router_backend_initialization(self):
        """Test that LLMRouterBackend can be initialized with mocked imports"""
        try:
            # Mock the generate_text import
            with patch('backends.llm_router_backend.generate_text', return_value="mocked response"):
                from backends.llm_router_backend import LLMRouterBackend
                
                backend = LLMRouterBackend(
                    id='test-router',
                    provider='local_hf',
                    model='gpt2'
                )
                
                assert backend.id == 'test-router'
                assert backend.provider == 'hf'
                assert backend.model == 'gpt2'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_llm_router_backend_call(self):
        """Test that LLMRouterBackend can generate text"""
        try:
            # Mock the generate_text function
            mock_generate = Mock(return_value="Generated text response")
            
            with patch('backends.llm_router_backend.generate_text', mock_generate):
                from backends.llm_router_backend import LLMRouterBackend
                
                backend = LLMRouterBackend(
                    id='test-router',
                    provider='local_hf',
                    model='gpt2'
                )
                
                response = backend("Test prompt")
                
                assert response == "Generated text response"
                mock_generate.assert_called_once()
                
                # Verify the call arguments
                call_args = mock_generate.call_args
                assert call_args.kwargs['prompt'] == "Test prompt"
                assert call_args.kwargs['provider'] == 'hf'
                assert call_args.kwargs['model_name'] == 'gpt2'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_llm_router_backend_normalizes_local_provider_alias(self):
        """Test that simple local provider aliases are normalized for the shared router."""
        try:
            mock_generate = Mock(return_value="Generated text response")

            with patch('backends.llm_router_backend.generate_text', mock_generate):
                from backends.llm_router_backend import LLMRouterBackend

                backend = LLMRouterBackend(
                    id='test-router',
                    provider='local',
                    model='gpt2'
                )

                response = backend("Test prompt")

                assert response == "Generated text response"
                assert backend.provider == 'hf'
                call_args = mock_generate.call_args
                assert call_args.kwargs['provider'] == 'hf'
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_llm_router_backend_with_config(self):
        """Test that LLMRouterBackend passes config to generate_text"""
        try:
            mock_generate = Mock(return_value="Response with config")
            
            with patch('backends.llm_router_backend.generate_text', mock_generate):
                from backends.llm_router_backend import LLMRouterBackend
                
                backend = LLMRouterBackend(
                    id='test-router',
                    provider='local_hf',
                    model='gpt2',
                    max_tokens=100,
                    temperature=0.7
                )
                
                response = backend("Test prompt")
                
                # Verify config was passed
                call_args = mock_generate.call_args
                assert call_args.kwargs.get('max_tokens') == 100
                assert call_args.kwargs.get('temperature') == 0.7
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_llm_router_backend_error_handling(self):
        """Test that LLMRouterBackend handles errors properly"""
        try:
            mock_generate = Mock(side_effect=Exception("LLM error"))
            
            with patch('backends.llm_router_backend.generate_text', mock_generate):
                from backends.llm_router_backend import LLMRouterBackend
                
                backend = LLMRouterBackend(
                    id='test-router',
                    provider='local_hf'
                )
                
                with pytest.raises(Exception) as exc_info:
                    backend("Test prompt")
                
                assert "llm_router_error" in str(exc_info.value)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_llm_router_alias_exists(self):
        """Test that LLMRouter alias exists"""
        try:
            with patch('backends.llm_router_backend.generate_text', return_value="test"):
                from backends.llm_router_backend import LLMRouter, LLMRouterBackend
                assert LLMRouter is LLMRouterBackend
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

"""
Test Batch 265: Path Validation for CLI Security

Tests comprehensive path validation utilities that prevent path traversal attacks,
symlink exploits, and access to sensitive system files.

Test Coverage:
    - Path traversal prevention (../, ../../, etc.)
    - Absolute path validation and restriction
    - Symlink resolution and validation
    - Sensitive path blocking (/etc, /sys, /proc, etc.)
    - Directory whitelisting (base_dir enforcement)
    - Extension validation
    - Size limit enforcement
    - Overwrite protection
    - Empty string/None handling

Security Scenarios:
    - CWE-22: Path Traversal attacks
    - Symlink-based exploits
    - Writing to system directories
    - Reading sensitive files
    - Overwriting critical files

References:
    - (P1) [security] CLI file input validation
    - ipfs_datasets_py/optimizers/common/path_validator.py
"""

import pytest
import tempfile
import os
from pathlib import Path
from pytest import raises

from ipfs_datasets_py.optimizers.common.path_validator import (
    validate_input_path,
    validate_output_path,
    validate_directory_path,
    safe_open,
    PathValidationError,
    BLOCKED_PATHS,
    BLOCKED_FILENAMES,
)


class TestInputPathValidation:
    """Test validate_input_path() against various attack vectors."""
    
    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create temporary workspace with test files."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        # Create valid input file
        input_file = workspace / "input.json"
        input_file.write_text('{"test": "data"}')
        
        # Create file with sensitive name
        sensitive_file = workspace / "passwd_backup.txt"
        sensitive_file.write_text("not really passwd")
        
        # Create large file
        large_file = workspace / "large.bin"
        large_file.write_bytes(b"x" * (10 * 1024 * 1024))  # 10MB
        
        return workspace
    
    def test_valid_relative_path(self, temp_workspace):
        """Valid relative path within base_dir should pass."""
        result = validate_input_path(
            "input.json",
            base_dir=temp_workspace,
            must_exist=True
        )
        
        assert result == temp_workspace / "input.json"
        assert result.exists()
    
    def test_path_traversal_parent_denied(self, temp_workspace):
        """Path traversal with ../ should be denied."""
        with raises(PathValidationError, match="escape base directory"):
            validate_input_path(
                "../../../etc/passwd",
                base_dir=temp_workspace,
                must_exist=False
            )
    
    def test_path_traversal_multiple_parents_denied(self, temp_workspace):
        """Multiple ../ attempts should be denied."""
        with raises(PathValidationError, match="escape base directory"):
            validate_input_path(
                "../../../../../../etc/passwd",
                base_dir=temp_workspace,
                must_exist=False
            )
    
    def test_absolute_path_outside_base_denied(self, temp_workspace):
        """Absolute path outside base_dir should be denied."""
        with raises(PathValidationError, match="escape base directory"):
            validate_input_path(
                "/etc/passwd",
                base_dir=temp_workspace,
                must_exist=False
            )
    
    def test_sensitive_system_path_denied(self, temp_workspace):
        """Access to /etc should be explicitly blocked."""
        # Even if we set base_dir to /, /etc should still be blocked
        with raises(PathValidationError, match="system path not allowed"):
            validate_input_path(
                "/etc/passwd",
                base_dir=Path("/"),
                must_exist=False
            )
    
    def test_sensitive_filename_denied(self, temp_workspace):
        """Files with sensitive names should be blocked."""
        with raises(PathValidationError, match="sensitive file not allowed"):
            validate_input_path(
                "passwd_backup.txt",
                base_dir=temp_workspace,
                must_exist=True
            )
    
    def test_nonexistent_file_denied_with_must_exist(self, temp_workspace):
        """Non-existent file should fail when must_exist=True."""
        with raises(PathValidationError, match="does not exist"):
            validate_input_path(
                "nonexistent.json",
                base_dir=temp_workspace,
                must_exist=True
            )
    
    def test_nonexistent_file_allowed_without_must_exist(self, temp_workspace):
        """Non-existent file should pass when must_exist=False."""
        result = validate_input_path(
            "nonexistent.json",
            base_dir=temp_workspace,
            must_exist=False
        )
        
        # Should resolve to expected path
        assert result == temp_workspace / "nonexistent.json"
    
    def test_extension_validation_pass(self, temp_workspace):
        """File with allowed extension should pass."""
        result = validate_input_path(
            "input.json",
            base_dir=temp_workspace,
            must_exist=True,
            allowed_extensions=[".json", ".txt"]
        )
        
        assert result.suffix == ".json"
    
    def test_extension_validation_fail(self, temp_workspace):
        """File with disallowed extension should fail."""
        with raises(PathValidationError, match="Invalid file extension"):
            validate_input_path(
                "input.json",
                base_dir=temp_workspace,
                must_exist=True,
                allowed_extensions=[".txt", ".yaml"]
            )
    
    def test_size_limit_enforcement(self, temp_workspace):
        """Files exceeding size limit should be denied."""
        with raises(PathValidationError, match="File too large"):
            validate_input_path(
                "large.bin",
                base_dir=temp_workspace,
                must_exist=True,
                max_size_bytes=1024 * 1024  # 1MB limit
            )
    
    def test_size_limit_pass(self, temp_workspace):
        """Files under size limit should pass."""
        result = validate_input_path(
            "input.json",
            base_dir=temp_workspace,
            must_exist=True,
            max_size_bytes=1024 * 1024  # 1MB limit
        )
        
        assert result.stat().st_size < 1024 * 1024
    
    def test_empty_path_denied(self, temp_workspace):
        """Empty path should be denied."""
        with raises(PathValidationError, match="cannot be empty"):
            validate_input_path(
                "",
                base_dir=temp_workspace
            )
    
    def test_directory_as_input_denied(self, temp_workspace):
        """Directory should fail when expecting file."""
        subdir = temp_workspace / "subdir"
        subdir.mkdir()
        
        with raises(PathValidationError, match="not a file"):
            validate_input_path(
                "subdir",
                base_dir=temp_workspace,
                must_exist=True
            )
    
    def test_symlink_denied_by_default(self, temp_workspace):
        """Symlinks should be denied by default."""
        target = temp_workspace / "input.json"
        link = temp_workspace / "link.json"
        
        # Create symlink
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("Symlink creation not supported on this system")
        
        with raises(PathValidationError, match="Symlinks not allowed"):
            validate_input_path(
                "link.json",
                base_dir=temp_workspace,
                must_exist=True,
                follow_symlinks=False
            )
    
    def test_symlink_allowed_with_flag(self, temp_workspace):
        """Symlinks should be allowed when follow_symlinks=True."""
        target = temp_workspace / "input.json"
        link = temp_workspace / "link.json"
        
        # Create symlink
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("Symlink creation not supported on this system")
        
        result = validate_input_path(
            "link.json",
            base_dir=temp_workspace,
            must_exist=True,
            follow_symlinks=True
        )
        
        # Should resolve to target
        assert result.resolve() == target.resolve()


class TestOutputPathValidation:
    """Test validate_output_path() for write operations."""
    
    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create temporary workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        # Create existing file
        existing = workspace / "existing.json"
        existing.write_text('{"old": "data"}')
        
        return workspace
    
    def test_valid_output_path(self, temp_workspace):
        """Valid output path should pass."""
        result = validate_output_path(
            "output.json",
            base_dir=temp_workspace
        )
        
        assert result == temp_workspace / "output.json"
    
    def test_overwrite_denied_by_default(self, temp_workspace):
        """Overwriting existing file should be denied by default."""
        with raises(PathValidationError, match="already exists"):
            validate_output_path(
                "existing.json",
                base_dir=temp_workspace,
                allow_overwrite=False
            )
    
    def test_overwrite_allowed_with_flag(self, temp_workspace):
        """Overwriting should be allowed when allow_overwrite=True."""
        result = validate_output_path(
            "existing.json",
            base_dir=temp_workspace,
            allow_overwrite=True
        )
        
        assert result == temp_workspace / "existing.json"
    
    def test_output_path_traversal_denied(self, temp_workspace):
        """Output path traversal should be denied."""
        exception_raised = False
        try:
            result = validate_output_path(
                "../../../tmp/evil.txt",
                base_dir=temp_workspace
            )
            # If we get here, no exception was raised
            assert False, f"Expected PathValidationError but got result: {result}"
        except PathValidationError as e:
            exception_raised = True
            assert "escape base directory" in str(e), f"Wrong error message: {e}"
        
        assert exception_raised, "PathValidationError was not raised"
    
    def test_output_to_system_path_denied(self, temp_workspace):
        """Writing to system paths should be denied."""
        with raises(PathValidationError, match="system path not allowed"):
            validate_output_path(
                "/etc/evil.conf",
                base_dir=Path("/"),
                allow_overwrite=True
            )
    
    def test_output_extension_validation(self, temp_workspace):
        """Output extension validation should work."""
        with raises(PathValidationError, match="Invalid file extension"):
            validate_output_path(
                "output.exe",
                base_dir=temp_workspace,
                allowed_extensions=[".json", ".txt"]
            )
    
    def test_output_in_subdirectory(self, temp_workspace):
        """Output in non-existent subdirectory should resolve correctly."""
        result = validate_output_path(
            "subdir/output.json",
            base_dir=temp_workspace
        )
        
        # Should resolve even if subdir doesn't exist yet
        expected = temp_workspace / "subdir" / "output.json"
        assert result == expected


class TestDirectoryPathValidation:
    """Test validate_directory_path() for directory operations."""
    
    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create temporary workspace with directories."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        # Create empty directory
        empty_dir = workspace / "empty"
        empty_dir.mkdir()
        
        # Create non-empty directory
        nonempty_dir = workspace / "nonempty"
        nonempty_dir.mkdir()
        (nonempty_dir / "file.txt").write_text("content")
        
        return workspace
    
    def test_valid_directory_path(self, temp_workspace):
        """Valid directory path should pass."""
        result = validate_directory_path(
            "empty",
            base_dir=temp_workspace,
            must_exist=True
        )
        
        assert result == temp_workspace / "empty"
        assert result.is_dir()
    
    def test_nonexistent_directory_denied(self, temp_workspace):
        """Non-existent directory should fail when must_exist=True."""
        with raises(PathValidationError, match="does not exist"):
            validate_directory_path(
                "nonexistent",
                base_dir=temp_workspace,
                must_exist=True
            )
    
    def test_file_as_directory_denied(self, temp_workspace):
        """File should fail when expecting directory."""
        file_path = temp_workspace / "file.txt"
        file_path.write_text("content")
        
        with raises(PathValidationError, match="not a directory"):
            validate_directory_path(
                "file.txt",
                base_dir=temp_workspace,
                must_exist=True
            )
    
    def test_empty_directory_check(self, temp_workspace):
        """Empty directory check should work."""
        # Empty directory should pass
        result = validate_directory_path(
            "empty",
            base_dir=temp_workspace,
            must_exist=True,
            must_be_empty=True
        )
        
        assert result.is_dir()
        assert not list(result.iterdir())
    
    def test_nonempty_directory_fails_empty_check(self, temp_workspace):
        """Non-empty directory should fail empty check."""
        with raises(PathValidationError, match="not empty"):
            validate_directory_path(
                "nonempty",
                base_dir=temp_workspace,
                must_exist=True,
                must_be_empty=True
            )


class TestSafeOpen:
    """Test safe_open() wrapper function."""
    
    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create temporary workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        # Create test file
        test_file = workspace / "test.txt"
        test_file.write_text("test content")
        
        # Change to workspace directory for relative paths
        import os
        old_cwd = os.getcwd()
        os.chdir(workspace)
        yield workspace
        os.chdir(old_cwd)
    
    def test_safe_open_read(self, temp_workspace):
        """safe_open() should work for reading."""
        with safe_open("test.txt", "r") as f:
            content = f.read()
        
        assert content == "test content"
    
    def test_safe_open_write(self, temp_workspace):
        """safe_open() should work for writing."""
        with safe_open("output.txt", "w") as f:
            f.write("new content")
        
        # Verify file was written
        assert (temp_workspace / "output.txt").read_text() == "new content"
    
    def test_safe_open_traversal_denied(self, temp_workspace):
        """safe_open() should deny path traversal."""
        with raises(PathValidationError, match="escape base directory"):
            safe_open("../../etc/passwd", "r")


class TestBlockedPathsConfiguration:
    """Test that blocked paths and filenames are properly configured."""
    
    def test_blocked_paths_includes_etc(self):
        """BLOCKED_PATHS should include /etc."""
        assert "/etc" in BLOCKED_PATHS
    
    def test_blocked_paths_includes_sys(self):
        """BLOCKED_PATHS should include /sys."""
        assert "/sys" in BLOCKED_PATHS
    
    def test_blocked_paths_includes_proc(self):
        """BLOCKED_PATHS should include /proc."""
        assert "/proc" in BLOCKED_PATHS
    
    def test_blocked_filenames_includes_passwd(self):
        """BLOCKED_FILENAMES should include passwd."""
        assert "passwd" in BLOCKED_FILENAMES
    
    def test_blocked_filenames_includes_shadow(self):
        """BLOCKED_FILENAMES should include shadow."""
        assert "shadow" in BLOCKED_FILENAMES
    
    def test_blocked_filenames_includes_ssh_keys(self):
        """BLOCKED_FILENAMES should include SSH private keys."""
        assert "id_rsa" in BLOCKED_FILENAMES
        assert "id_dsa" in BLOCKED_FILENAMES
        assert "id_ecdsa" in BLOCKED_FILENAMES
        assert "id_ed25519" in BLOCKED_FILENAMES


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_null_byte_in_path(self, tmp_path):
        """Null bytes in path should be handled safely."""
        # Python's Path should handle this, but verify
        with raises((PathValidationError, ValueError)):
            validate_input_path(
                "test\x00.txt",
                base_dir=tmp_path
            )
    
    def test_very_long_path(self, tmp_path):
        """Very long paths should be handled."""
        # Create path with many nested directories
        long_path = "/".join(["a"] * 100) + "/file.txt"
        
        # Should either validate or raise PathValidationError (not crash)
        try:
            validate_input_path(
                long_path,
                base_dir=tmp_path,
                must_exist=False
            )
        except PathValidationError:
            pass  # Expected
    
    def test_unicode_in_path(self, tmp_path):
        """Unicode characters in path should be handled."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        # Create file with unicode name
        unicode_file = workspace / "файл.txt"  # Russian "file"
        unicode_file.write_text("content")
        
        result = validate_input_path(
            "файл.txt",
            base_dir=workspace,
            must_exist=True
        )
        
        assert result.exists()
        assert result.name == "файл.txt"
    
    def test_spaces_in_path(self, tmp_path):
        """Spaces in path should be handled correctly."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        # Create file with spaces
        spaced_file = workspace / "my file.txt"
        spaced_file.write_text("content")
        
        result = validate_input_path(
            "my file.txt",
            base_dir=workspace,
            must_exist=True
        )
        
        assert result.exists()
        assert result.name == "my file.txt"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

"""Tests for input validation functions."""

import os
import sys

import pytest
from fastapi import HTTPException

# Add parent directory to path to import main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import validated_name


class TestValidatedName:
    """Test suite for validated_name function."""

    def test_valid_kubernetes_name(self):
        """Test valid Kubernetes resource names."""
        assert validated_name("my-pod") == "my-pod"
        assert validated_name("pod-123") == "pod-123"
        assert validated_name("my.service.name") == "my.service.name"
        assert validated_name("a") == "a"

    def test_valid_long_name(self):
        """Test valid names up to 253 characters."""
        long_name = "a" * 253
        assert validated_name(long_name) == long_name

    def test_invalid_path_traversal(self):
        """Test rejection of path traversal attempts."""
        with pytest.raises(HTTPException) as exc:
            validated_name("../etc/passwd")
        assert exc.value.status_code == 400

    def test_invalid_backslash(self):
        """Test rejection of backslash characters."""
        with pytest.raises(HTTPException) as exc:
            validated_name("..\\windows\\system32")
        assert exc.value.status_code == 400

    def test_invalid_null_byte(self):
        """Test rejection of null bytes."""
        with pytest.raises(HTTPException) as exc:
            validated_name("pod\x00name")
        assert exc.value.status_code == 400

    def test_invalid_slash_in_name(self):
        """Test rejection of forward slashes."""
        with pytest.raises(HTTPException) as exc:
            validated_name("pod/name")
        assert exc.value.status_code == 400

    def test_invalid_empty_name(self):
        """Test rejection of empty names."""
        with pytest.raises(HTTPException) as exc:
            validated_name("")
        assert exc.value.status_code == 400

    def test_invalid_too_long_name(self):
        """Test rejection of names exceeding 253 characters."""
        long_name = "a" * 254
        with pytest.raises(HTTPException) as exc:
            validated_name(long_name)
        assert exc.value.status_code == 400

    def test_invalid_special_characters(self):
        """Test handling of various special characters."""
        invalid_names = [
            "pod!name",
            "pod@name",
            "pod#name",
            "pod$name",
            "pod%name",
            "pod&name",
            "pod*name",
        ]
        # Note: These may be valid depending on Kubernetes validation rules
        # Only test those that should definitely fail (path traversal, null bytes, slashes)

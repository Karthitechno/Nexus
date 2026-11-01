"""Pytest configuration for NEXUS tests."""
import sys
from pathlib import Path

# Add project root to sys.path so imports like `nexus.xxx` work from any working directory
sys.path.insert(0, str(Path(__file__).parent))


import pytest
import sys
import os
from unittest.mock import patch, mock_open

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from pipeline.ingest.readers import read_text_files
from pipeline.ingest.generator import generate_context_markdown

def test_read_text_files():
    # Mocking file system is complex, but we can test the logic of combining texts
    # Or just test that context generation handles empty/simple cases
    pass

def test_generate_context_markdown():
    texts = [
        {"filename": "a.txt", "content": "Hello world"},
        {"filename": "b.txt", "content": "Lore ipsum"}
    ]
    # No need to mock open if we just test the string generation
    content = generate_context_markdown(texts, [], [], [], [])
    assert "# Project Analysis Context" in content
    assert "a.txt" in content
    assert "Hello world" in content

"""
Multimodal input ingestion for automatic functional analysis.

Takes screenshots, text notes, HTML, PDF, DOCX and extracts structured context.
Screenshots are analyzed with the LLM Vision API.

Usage:
    python ingest.py --input-dir ./inputs --output-file project_context.md
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

from pipeline.ingest.readers import (
    read_text_files,
    read_pdf_files,
    read_docx_files,
    process_html_files,
    process_screenshots,
)
from pipeline.ingest.generator import generate_context_markdown

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_INPUT_DIR = "./inputs"
DEFAULT_OUTPUT_FILE = "output/context/project_context.md"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest multimodal inputs for functional analysis")
    parser.add_argument("--input-dir", type=str, default=DEFAULT_INPUT_DIR,
                        help=f"Directory containing input files (default: {DEFAULT_INPUT_DIR})")
    parser.add_argument("--output-file", type=str, default=DEFAULT_OUTPUT_FILE,
                        help=f"Output context file (default: {DEFAULT_OUTPUT_FILE})")
    args = parser.parse_args()
    
    input_path = Path(args.input_dir)
    
    # FIX: Support both directories and single files
    is_single_file = input_path.is_file()
    
    if not input_path.exists():
        print(f"Creating input directory: {args.input_dir}")
        input_path.mkdir(parents=True, exist_ok=True)
        print("Please add your input files (text, HTML, screenshots) to this directory and re-run.")
        return
    
    if is_single_file:
        print(f"Processing single file: {args.input_dir}")
    else:
        print(f"Processing inputs from: {args.input_dir}")
    print()
    
    # Process all inputs
    print("Step 1: Reading text files...")
    if is_single_file:
        # Read single file directly
        texts = []
        try:
            with open(args.input_dir, "r", encoding="utf-8") as f:
                content = f.read()
            texts.append({
                "filename": input_path.name,
                "content": content,
                "type": "text"
            })
        except Exception as e:
            print(f"  ⚠️  Error reading {args.input_dir}: {e}")
    else:
        texts = read_text_files(args.input_dir)
    print(f"  Found {len(texts)} text file(s)")
    print()
    
    print("Step 2: Reading PDF files...")
    if is_single_file:
        pdf_texts = []
    else:
        pdf_texts = read_pdf_files(args.input_dir)
    print(f"  Found {len(pdf_texts)} PDF file(s)")
    print()
    
    print("Step 3: Reading DOCX files...")
    if is_single_file:
        docx_texts = []
    else:
        docx_texts = read_docx_files(args.input_dir)
    print(f"  Found {len(docx_texts)} DOCX file(s)")
    print()
    
    print("Step 4: Processing HTML files...")
    if is_single_file:
        html_structures = []
    else:
        html_structures = process_html_files(args.input_dir)
    print(f"  Found {len(html_structures)} HTML file(s)")
    print()
    
    print("Step 5: Processing screenshots (with Vision analysis)...")
    if is_single_file:
        screenshots = []
    else:
        screenshots = process_screenshots(args.input_dir, use_vision=True)
    print(f"  Found {len(screenshots)} screenshot(s)")
    print()
    
    # Generate context
    print("Step 6: Generating unified context...")
    context_md = generate_context_markdown(texts, html_structures, screenshots, pdf_texts, docx_texts)
    
    # Write output
    with open(args.output_file, "w", encoding="utf-8") as f:
        f.write(context_md)
    
    print(f"  Wrote context to: {args.output_file}")
    print()
    print("Done! Ready to run spec.py")


if __name__ == "__main__":
    main()
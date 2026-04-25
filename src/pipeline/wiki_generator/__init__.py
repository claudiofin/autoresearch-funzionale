"""
LLM Wiki Generator - Crea la Memory Bank per gli Agenti AI.

Usage:
    from pipeline.wiki_generator import main
    main()
"""

import os
import sys
import argparse

from pipeline.wiki_generator.wiki_generator import generate_wiki


def main():
    parser = argparse.ArgumentParser(
        description="LLM Wiki Generator - Crea la Memory Bank per gli Agenti AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py wiki-generator
    python run.py wiki-generator --force
    python run.py wiki-generator --context output/context/project_context.md --output-dir output/llm_wiki
        """
    )
    parser.add_argument("--context", type=str, default="output/context/project_context.md",
                        help="Path al file project_context.md")
    parser.add_argument("--output-dir", type=str, default="output/llm_wiki",
                        help="Directory di output per la LLM Wiki")
    parser.add_argument("--base-output-dir", type=str, default="output",
                        help="Directory base da scansionare per l'indice")
    parser.add_argument("--force", action="store_true",
                        help="Force regeneration of existing files")
    
    args = parser.parse_args()
    
    generate_wiki(
        context_path=args.context,
        output_dir=args.output_dir,
        base_output_dir=args.base_output_dir,
        force=args.force
    )


if __name__ == "__main__":
    main()
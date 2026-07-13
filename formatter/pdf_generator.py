"""Converts rendered HTML to a PDF file using WeasyPrint."""

import os
from datetime import datetime


def html_to_pdf(html_content: str, issue_date: str) -> str:
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        print("[PDF] WeasyPrint not installed. Skipping PDF generation.")
        return ""

    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)

    safe_date = issue_date.replace(" ", "_").replace(",", "")
    filename = f"ai_dispatch_{safe_date}.pdf"
    filepath = os.path.join(output_dir, filename)

    print(f"[PDF] Generating {filename}...")
    try:
        HTML(string=html_content).write_pdf(
            filepath,
            stylesheets=[
                CSS(string="@page { size: A4; margin: 1cm; }")
            ],
        )
        print(f"[PDF] Saved to {filepath}")
        return filepath
    except Exception as e:
        print(f"[PDF] Generation failed: {e}")
        return ""

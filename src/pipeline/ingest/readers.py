"""
File readers for multimodal input ingestion.
Handles text, PDF, DOCX, HTML, and screenshot files.
"""

import os
import base64
from pathlib import Path

from bs4 import BeautifulSoup

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import LLM_CONFIG, DEFAULT_PROVIDER


# ---------------------------------------------------------------------------
# Text Files
# ---------------------------------------------------------------------------

def read_text_files(input_dir: str) -> list[dict]:
    """Read all .txt and .md files from input directory."""
    texts = []
    input_path = Path(input_dir)
    
    for ext in ["*.txt", "*.md"]:
        for file_path in input_path.glob(ext):
            try:
                content = file_path.read_text(encoding="utf-8")
                texts.append({
                    "type": "text",
                    "filename": file_path.name,
                    "content": content
                })
                print(f"  Loaded text: {file_path.name}")
            except Exception as e:
                print(f"  Warning: Could not read {file_path.name}: {e}")
    
    return texts


# ---------------------------------------------------------------------------
# PDF Files
# ---------------------------------------------------------------------------

def read_pdf_files(input_dir: str) -> list[dict]:
    """Read all PDF files and extract text content."""
    texts = []
    input_path = Path(input_dir)
    
    try:
        import pypdf
    except ImportError:
        print("  ⚠️  pypdf not installed - PDFs not supported. Install: pip install pypdf")
        return texts
    
    for file_path in input_path.glob("*.pdf"):
        try:
            reader = pypdf.PdfReader(str(file_path))
            content = ""
            for page in reader.pages:
                content += page.extract_text() + "\n\n"
            
            texts.append({
                "type": "pdf",
                "filename": file_path.name,
                "content": content.strip()
            })
            print(f"  Loaded PDF: {file_path.name} ({len(reader.pages)} pages)")
        except Exception as e:
            print(f"  Warning: Could not read {file_path.name}: {e}")
    
    return texts


# ---------------------------------------------------------------------------
# DOCX Files
# ---------------------------------------------------------------------------

def read_docx_files(input_dir: str) -> list[dict]:
    """Read all DOCX files and extract text content."""
    texts = []
    input_path = Path(input_dir)
    
    try:
        import docx
    except ImportError:
        print("  ⚠️  python-docx not installed - DOCXs not supported. Install: pip install python-docx")
        return texts
    
    for file_path in input_path.glob("*.docx"):
        try:
            doc = docx.Document(str(file_path))
            content = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            
            texts.append({
                "type": "docx",
                "filename": file_path.name,
                "content": content.strip()
            })
            print(f"  Loaded DOCX: {file_path.name}")
        except Exception as e:
            print(f"  Warning: Could not read {file_path.name}: {e}")
    
    return texts


# ---------------------------------------------------------------------------
# HTML Files
# ---------------------------------------------------------------------------

def extract_html_structure(html_content: str, filename: str) -> dict:
    """Extract semantic structure from HTML file."""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script and style tags
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    
    extracted = {
        "filename": filename,
        "title": soup.title.string if soup.title else "Untitled",
        "forms": [],
        "buttons": [],
        "inputs": [],
        "links": [],
        "headings": [],
        "semantic_structure": []
    }
    
    # Extract forms
    for form in soup.find_all("form"):
        form_data = {
            "action": form.get("action", ""),
            "method": form.get("method", "GET"),
            "fields": []
        }
        for field in form.find_all(["input", "select", "textarea"]):
            field_info = {
                "type": field.get("type", "text"),
                "name": field.get("name", ""),
                "id": field.get("id", ""),
                "required": field.has_attr("required"),
                "pattern": field.get("pattern", ""),
                "placeholder": field.get("placeholder", ""),
            }
            form_data["fields"].append(field_info)
        extracted["forms"].append(form_data)
    
    # Extract buttons
    for btn in soup.find_all(["button", "input[type='button']", "input[type='submit']"]):
        extracted["buttons"].append({
            "text": btn.get_text(strip=True),
            "type": btn.get("type", "button"),
            "id": btn.get("id", ""),
            "onclick": btn.get("onclick", ""),
            "formaction": btn.get("formaction", ""),
        })
    
    # Extract inputs (outside forms too)
    for inp in soup.find_all("input"):
        extracted["inputs"].append({
            "type": inp.get("type", "text"),
            "name": inp.get("name", ""),
            "id": inp.get("id", ""),
            "required": inp.has_attr("required"),
            "pattern": inp.get("pattern", ""),
            "placeholder": inp.get("placeholder", ""),
            "value": inp.get("value", ""),
        })
    
    # Extract links
    for link in soup.find_all("a", href=True):
        extracted["links"].append({
            "text": link.get_text(strip=True),
            "href": link.get("href", ""),
            "target": link.get("target", ""),
        })
    
    # Extract headings
    for i in range(1, 7):
        for h in soup.find_all(f"h{i}"):
            extracted["headings"].append({
                "level": i,
                "text": h.get_text(strip=True),
                "id": h.get("id", ""),
            })
    
    # Build semantic structure (simplified DOM tree)
    def extract_semantic(tag):
        result = []
        for child in tag.children:
            if child.name:
                node = {
                    "tag": child.name,
                    "id": child.get("id", ""),
                    "class": child.get("class", []),
                    "text": child.get_text(strip=True)[:100] if child.get_text(strip=True) else "",
                }
                if node["text"] or node["id"] or node["class"]:
                    result.append(node)
                result.extend(extract_semantic(child))
        return result
    
    body = soup.body if soup.body else soup
    extracted["semantic_structure"] = extract_semantic(body)
    
    return extracted


def process_html_files(input_dir: str) -> list[dict]:
    """Process all HTML files and extract structure."""
    html_structures = []
    input_path = Path(input_dir)
    
    for ext in ["*.html", "*.htm"]:
        for file_path in input_path.glob(ext):
            try:
                content = file_path.read_text(encoding="utf-8")
                structure = extract_html_structure(content, file_path.name)
                html_structures.append({
                    "type": "html",
                    "filename": file_path.name,
                    "structure": structure
                })
                print(f"  Extracted HTML structure: {file_path.name}")
            except Exception as e:
                print(f"  Warning: Could not process {file_path.name}: {e}")
    
    return html_structures


# ---------------------------------------------------------------------------
# Screenshots (Vision API)
# ---------------------------------------------------------------------------

def analyze_screenshot_with_vision(image_path: str, mime_type: str) -> str:
    """
    Analyze a screenshot with the LLM Vision API.
    Extracts: CTAs, input fields, error states, layout, visible flows.
    """
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        return "⚠️  LLM_API_KEY not set - screenshot analysis unavailable"
    
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    
    if provider in LLM_CONFIG:
        base_url = os.getenv("LLM_BASE_URL", LLM_CONFIG[provider]["base_url"])
        model = os.getenv("LLM_MODEL", LLM_CONFIG[provider]["model"])
    else:
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            return f"⚠️  Provider '{provider}' not configured for Vision"
    
    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    
    prompt = """You are a UI/UX Analyst. Analyze this screenshot and extract ALL functional information.

Extract and list:
1. **All visible UI elements**: buttons, inputs, links, forms, cards, lists, modals
2. **All Call-to-Action (CTA)**: what actions can the user take?
3. **All input fields**: what data can the user enter? (with labels, placeholders, validation hints)
4. **Error states visible**: are there any error messages, validation errors, empty states?
5. **Navigation elements**: menus, breadcrumbs, tabs, back buttons
6. **Layout structure**: what's the visual hierarchy? What's the primary action?
7. **Data displayed**: what information is shown? (lists, tables, charts, stats)
8. **User flow implied**: what is the user trying to accomplish on this screen?

Be SPECIFIC - list every element you see. Do NOT generalize.
"""
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert UI/UX Analyst. Analyze screenshots and extract detailed functional information."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{image_data}",
                        "detail": "high"
                    }}
                ]}
            ],
            max_tokens=2048,
            temperature=0.3,
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        return f"⚠️  Vision analysis error: {e}"


def process_screenshots(input_dir: str, use_vision: bool = True) -> list[dict]:
    """
    Process screenshot files and analyze with Vision API.
    """
    screenshots = []
    input_path = Path(input_dir)
    
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        for file_path in input_path.glob(ext):
            try:
                suffix = file_path.suffix.lstrip(".").lower()
                if suffix == "jpg" or suffix == "jpeg":
                    mime_type = "image/jpeg"
                elif suffix == "png":
                    mime_type = "image/png"
                elif suffix == "webp":
                    mime_type = "image/webp"
                else:
                    mime_type = f"image/{suffix}"
                
                screenshot = {
                    "type": "screenshot",
                    "filename": file_path.name,
                    "mime_type": mime_type,
                    "file_path": str(file_path),
                    "analysis": None,
                }
                
                if use_vision and os.getenv("LLM_API_KEY"):
                    print(f"  🔍 Analyzing screenshot with Vision: {file_path.name}...")
                    analysis = analyze_screenshot_with_vision(str(file_path), mime_type)
                    screenshot["analysis"] = analysis
                else:
                    screenshot["analysis"] = "⚠️  Vision unavailable (LLM_API_KEY not set)"
                
                screenshots.append(screenshot)
                print(f"  ✓ Processed: {file_path.name}")
                
            except Exception as e:
                print(f"  Warning: Could not process {file_path.name}: {e}")
    
    return screenshots
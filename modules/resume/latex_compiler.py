"""
modules/resume/latex_compiler.py — RenderCV + pdflatex/xelatex PDF compilation.
Pipeline: YAML → (RenderCV) → LaTeX → PDF
Security: Filename sanitization prevents path traversal.
"""
import os
import re
import stat
import shutil
import subprocess
from pathlib import Path

from shared.logger import get_logger
from shared.config_validator import load_settings

logger = get_logger(__name__)

RESUMES_DIR = Path("resumes")


def compile_resume(yaml_path: Path, company: str, role: str) -> Path | None:
    """
    Compile a tailored YAML resume to PDF using RenderCV.

    Args:
        yaml_path: Path to tailored resume YAML
        company: Company name (for output filename)
        role: Role name (for output filename)

    Returns:
        Path to compiled PDF, or None if compilation fails
    """
    settings = load_settings()
    latex_engine = settings.get("resume", {}).get("latex_engine", "xelatex")

    # Sanitize output filename
    safe_company = re.sub(r'[^a-zA-Z0-9-]', '-', company.lower())[:40]
    safe_role = re.sub(r'[^a-zA-Z0-9-]', '-', role.lower())[:40]
    pdf_filename = f"{safe_company}-{safe_role}.pdf"
    pdf_path = RESUMES_DIR / pdf_filename

    RESUMES_DIR.mkdir(exist_ok=True)

    # --- Method 1: Try RenderCV (preferred) ---
    if shutil.which("rendercv"):
        result = _compile_with_rendercv(yaml_path, pdf_path)
        if result:
            _secure_file(pdf_path)
            return pdf_path
        logger.warning("RenderCV compilation failed, trying fallback")

    # --- Method 2: Fallback to pdflatex/xelatex if LaTeX available ---
    if shutil.which(latex_engine) or shutil.which("pdflatex"):
        engine = latex_engine if shutil.which(latex_engine) else "pdflatex"
        result = _compile_with_latex(yaml_path, pdf_path, engine)
        if result:
            _secure_file(pdf_path)
            return pdf_path

    logger.error(
        f"PDF compilation failed for {company}/{role}. "
        "Ensure RenderCV is installed: pip install rendercv"
    )
    return None


def _compile_with_rendercv(yaml_path: Path, pdf_path: Path) -> bool:
    """Compile using RenderCV CLI."""
    try:
        # RenderCV outputs to a 'rendercv_output' subdirectory
        result = subprocess.run(
            ["rendercv", "render", str(yaml_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(yaml_path.parent),
        )

        if result.returncode != 0:
            logger.error(f"RenderCV error: {result.stderr[:500]}")
            return False

        # Move generated PDF to target path
        output_dir = yaml_path.parent / "rendercv_output"
        generated_pdfs = list(output_dir.glob("*.pdf"))

        if not generated_pdfs:
            logger.error("RenderCV ran but produced no PDF")
            return False

        shutil.move(str(generated_pdfs[0]), str(pdf_path))
        logger.info(f"RenderCV compiled: {pdf_path}")
        return True

    except subprocess.TimeoutExpired:
        logger.error("RenderCV compilation timed out (120s)")
        return False
    except Exception as e:
        logger.error(f"RenderCV exception: {e}")
        return False


def _compile_with_latex(yaml_path: Path, pdf_path: Path, engine: str) -> bool:
    """
    Direct LaTeX compilation fallback.
    Requires a .tex template file alongside the YAML.
    """
    tex_path = yaml_path.with_suffix(".tex")

    if not tex_path.exists():
        logger.warning(f"No .tex template found at {tex_path} for direct LaTeX compilation")
        return False

    try:
        # Run LaTeX twice for proper cross-references
        for _ in range(2):
            result = subprocess.run(
                [engine, "-interaction=nonstopmode", str(tex_path)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(tex_path.parent),
            )
            if result.returncode != 0 and "Fatal" in result.stdout:
                logger.error(f"LaTeX compilation error: {result.stdout[-500:]}")
                return False

        # Move generated PDF
        generated_pdf = tex_path.with_suffix(".pdf")
        if generated_pdf.exists():
            shutil.move(str(generated_pdf), str(pdf_path))
            logger.info(f"LaTeX compiled: {pdf_path}")
            return True

        return False

    except subprocess.TimeoutExpired:
        logger.error("LaTeX compilation timed out")
        return False
    except Exception as e:
        logger.error(f"LaTeX exception: {e}")
        return False


def _secure_file(path: Path) -> None:
    """Set file permissions to owner read/write only (600)."""
    if path.exists():
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def get_pdf_path(company: str, role: str) -> Path:
    """Get the expected PDF path for a given company/role."""
    safe_company = re.sub(r'[^a-zA-Z0-9-]', '-', company.lower())[:40]
    safe_role = re.sub(r'[^a-zA-Z0-9-]', '-', role.lower())[:40]
    return RESUMES_DIR / f"{safe_company}-{safe_role}.pdf"

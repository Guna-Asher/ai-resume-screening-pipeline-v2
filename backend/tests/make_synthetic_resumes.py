"""Generate the SYNTHETIC validation batch (50 files) and its answer key.

Everything here is fabricated: invented names, example.com emails, invented projects. It is NOT the
assignment's provided dataset. It exists so the pipeline can be exercised on a ~50-resume batch with
different layouts / section names, and checked against known expected outcomes.

    docker compose run --rm backend python tests/make_synthetic_resumes.py \
        /app/samples/synthetic_resumes /app/samples/synthetic_manifest.json
"""

import json
import random
import sys
from pathlib import Path

from pdf_utils import make_pdf

FIRST = ["Aarav", "Beatrice", "Chen", "Daria", "Emeka", "Farah", "Gustav", "Hana", "Ivan", "Jamila",
         "Kofi", "Lena", "Mateo", "Noor", "Oskar", "Priya", "Quinn", "Rosa", "Sven", "Tara"]
LAST = ["Alder", "Bishop", "Castillo", "Dunmore", "Eriksen", "Fontaine", "Garrido", "Hollis", "Ibarra",
        "Jovanovic", "Kowalski", "Lindgren", "Moreau", "Nakamura", "Okafor", "Petrov", "Quintero",
        "Rasmussen", "Sandoval", "Tanaka"]

PY_BACKEND = ["Python", "Java", "JavaScript", "SQL", "FastAPI", "LangChain", "LangGraph", "React", "GCP",
              "Docker", "PostgreSQL", "Redis"]

# archetype -> content and the outcome the pipeline is expected to give it
ARCHETYPES = {
    "strong_agentic": dict(expect="eligible", layouts=["standard", "titlecase", "pipe", "tech", "flat"],
        skills=PY_BACKEND,
        projects=[("Research Assistant Agent", ["Built a stateful agentic workflow with retrieval, tool calling, orchestration and an evaluation pipeline",
                   "Implemented embeddings and vector search with document chunking over a Chroma vector store, with citations",
                   "Async FastAPI backend with PostgreSQL and Redis caching, deployed on GCP Cloud Run using Docker"], "Python, LangGraph, FastAPI")],
        experience=[("Backend Intern, Acme Corp", ["Developed Python microservices using FastAPI and wrote pytest unit tests", "Added structured logging and retry error handling"])]),
    "rag_pipeline": dict(expect="eligible", layouts=["standard", "titlecase", "inline", "pipe", "tech", "flat"],
        skills=["Python", "FastAPI", "Docker"],
        projects=[("Document QA", ["Built a RAG pipeline with document chunking, embeddings, vector retrieval and citations",
                   "Exposed the service through a FastAPI REST API with PostgreSQL storage"], "Python, FAISS, FastAPI")], experience=[]),
    "thin_wrapper": dict(expect="eligible", layouts=["standard", "titlecase", "inline", "pipe"],
        skills=["Python", "Flask"], projects=[("Support Chatbot", ["We created a chatbot using OpenAI API"], "Python, OpenAI API")], experience=[]),
    "java_react_python_ai": dict(expect="eligible", layouts=["standard", "titlecase", "inline", "tech"],
        skills=["Java", "JavaScript", "TypeScript", "Python", "React", "Next.js"],
        projects=[("Knowledge Assistant", ["Built a RAG pipeline with embeddings and FAISS vector retrieval", "Next.js frontend and a Python API deployed with Docker"], "Python, LangChain, React")], experience=[]),
    "skills_only_frameworks": dict(expect="eligible", layouts=["standard", "titlecase", "inline", "pipe"],
        skills=["Python", "LangChain", "LangGraph", "LlamaIndex", "RAG", "Google ADK"],
        projects=[("Inventory Tracker", ["Built a CRUD app with Django and SQLite"], "Python, Django")], experience=[]),
    "work_experience_ai": dict(expect="eligible", layouts=["standard", "titlecase", "pipe", "tech", "flat"],
        skills=["Python", "SQL"], projects=[],
        experience=[("ML Engineer Intern, DataCo", ["Developed an LLM application in Python using LangChain and OpenAI API for internal document search",
                    "Implemented embeddings with a vector store and reranking"])]),
    "summary_claim_only": dict(expect="eligible", layouts=["standard", "flat"],
        summary="Built RAG applications and agentic workflows in Python.", skills=["Python"], projects=[], experience=[]),
    "no_python": dict(expect="rejected", layouts=["standard", "titlecase", "inline", "pipe", "flat"],
        skills=["Java", "Spring Boot", "React", "JavaScript"],
        projects=[("Smart Search", ["Built a RAG pipeline in Java with embeddings and vector search"], "Java, Spring")], experience=[]),
    "python_no_ai": dict(expect="rejected", layouts=["standard", "titlecase", "inline", "tech", "flat"],
        skills=["Python", "Django", "PostgreSQL"],
        projects=[("Online Store", ["Built an e-commerce backend in Python with Django and PostgreSQL"], "Python, Django")], experience=[],
        extra=["CERTIFICATIONS", "Watched an AI tutorial about LLMs on YouTube"]),
    "tutorial_only_python": dict(expect="rejected", layouts=["standard", "titlecase", "pipe"],
        summary="I watched a Python tutorial last month.", skills=["Java", "Spring"],
        projects=[("Support Bot", ["Built a RAG pipeline with embeddings and vector search in Java"], "Java")], experience=[]),
    "classic_ml_only": dict(expect="rejected", layouts=["standard", "titlecase", "inline", "tech"],
        skills=["Python", "scikit-learn", "pandas", "NumPy"],
        projects=[("Churn Model", ["Built a machine learning classifier with scikit-learn and pandas to predict customer churn", "Evaluated models with cross-validation"], "Python, scikit-learn")], experience=[]),
    "non_ai_agent_role": dict(expect="rejected", layouts=["standard", "titlecase", "pipe"],
        skills=["Python", "Excel"], projects=[],
        experience=[("Customer Support Agent, ShopCo", ["Managed customer support agents and wrote Python scripts for reports"])]),
}

HEADINGS = {  # layout -> (skills, projects, experience, education, summary)
    "standard": ("SKILLS", "PROJECTS", "EXPERIENCE", "EDUCATION", "SUMMARY"),
    "titlecase": ("Technical Skills", "Selected Projects", "Professional Experience", "Education", "Profile"),
    "inline": ("Skills", "Projects", "Internship Experience", "Education", "Summary"),
    "pipe": ("CORE COMPETENCIES", "PROJECT EXPERIENCE", "WORK HISTORY", "EDUCATION", "OBJECTIVE"),
    "tech": ("TECHNOLOGIES", "PERSONAL PROJECTS", "INTERNSHIPS", "ACADEMIC BACKGROUND", "ABOUT ME"),
}

GITHUB_FORMS = ["", "github.com/{u}", "https://github.com/{u}", "https://www.github.com/{u}/", ""]


def render(name: str, email: str | None, github: str, arch: dict, layout: str) -> list[str]:
    lines: list[str] = []
    contact = " | ".join(x for x in [email, github] if x)
    if layout == "pipe":
        lines.append(f"{name.upper()} | {contact}" if contact else name.upper())
    else:
        lines += [name] + ([contact] if contact else [])
    lines.append("")

    if layout == "flat":  # no section headings at all
        if arch.get("summary"):
            lines.append(arch["summary"])
        for title, bullets, tech in arch["projects"]:
            lines.append(f"{title}: " + " ".join(bullets))
        for title, bullets in arch["experience"]:
            lines.append(f"{title}. " + " ".join(bullets))
        lines.append(f"Technical stack: {', '.join(arch['skills'])}")
        return lines

    skills_h, proj_h, exp_h, edu_h, sum_h = HEADINGS[layout]
    if arch.get("summary"):
        lines += [sum_h, arch["summary"], ""]
    if layout == "inline":
        lines += [f"{skills_h}: {', '.join(arch['skills'])}", ""]
    else:
        lines += [skills_h, ", ".join(arch["skills"]), ""]
    if arch["projects"]:
        lines.append(proj_h)
        for title, bullets, tech in arch["projects"]:
            lines.append(f"{title} | {tech}" if layout in ("standard", "pipe") else title)
            if layout in ("titlecase", "inline", "tech"):
                lines.append(f"Tech: {tech}")
            lines += [f"- {b}" for b in bullets]
            lines.append("")
    if arch["experience"]:
        lines.append(exp_h)
        for title, bullets in arch["experience"]:
            lines.append(title)
            lines += [f"- {b}" for b in bullets]
        lines.append("")
    if arch.get("extra"):
        lines += [arch["extra"][0], arch["extra"][1], ""]
    lines += [edu_h, "B.Sc. Computer Science, Example University"]
    return lines


def generate(out_dir: Path, manifest_path: Path) -> dict:
    rng = random.Random(7)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    names = [f"{f} {l}" for f in FIRST for l in LAST]
    rng.shuffle(names)
    archetypes = list(ARCHETYPES)
    first_valid: tuple[str, bytes] | None = None

    for i in range(45):
        key = archetypes[i % len(archetypes)]
        arch = ARCHETYPES[key]
        layout = arch["layouts"][(i // len(archetypes)) % len(arch["layouts"])]
        name = names[i]
        slug = name.lower().replace(" ", ".")
        email = None if i % 11 == 7 else f"{slug}@example.com"  # a few without email
        gh_form = GITHUB_FORMS[i % len(GITHUB_FORMS)]
        github = gh_form.format(u=f"synthetic-cand-{i:02d}") if gh_form else ""
        if i % 13 == 5:
            name = name.replace("a", "á", 1)  # accented characters
        data = make_pdf_latin1(render(name, email, github, arch, layout))
        filename = f"cand_{i + 1:03d}.pdf"
        (out_dir / filename).write_bytes(data)
        manifest[filename] = {"archetype": key, "layout": layout, "expected": arch["expect"]}
        if first_valid is None:
            first_valid = (filename, data)

    assert first_valid is not None
    specials = {
        "cand_046_corrupt.pdf": (b"%PDF-1.4 this is not a real pdf", {"archetype": "corrupt_pdf", "expected": "failed"}),
        "cand_047_empty.pdf": (b"", {"archetype": "empty_file", "expected": "failed"}),
        "cand_048_notes.docx": (b"PK\x03\x04 not supported", {"archetype": "unsupported_type", "expected": "failed"}),
        "cand_049_copy.pdf": (first_valid[1], {"archetype": "byte_duplicate", "expected": "duplicate", "duplicate_of": first_valid[0]}),
    }
    reexport = make_pdf_latin1([""] + render_lines_from(out_dir / first_valid[0], None))
    specials["cand_050_reexport.pdf"] = (reexport, {"archetype": "text_duplicate", "expected": "duplicate", "duplicate_of": first_valid[0]})
    for filename, (data, meta) in specials.items():
        (out_dir / filename).write_bytes(data)
        manifest[filename] = meta

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def make_pdf_latin1(lines: list[str]) -> bytes:
    return make_pdf([ln.encode("latin-1", "replace").decode("latin-1") for ln in lines])


def render_lines_from(pdf_path: Path, _unused) -> list[str]:
    """Text of an existing generated PDF as lines (to build a same-text, different-bytes re-export)."""
    from pypdf import PdfReader

    return (PdfReader(str(pdf_path)).pages[0].extract_text() or "").split("\n")


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/synthetic_resumes")
    key_file = Path(sys.argv[2] if len(sys.argv) > 2 else "samples/synthetic_manifest.json")
    result = generate(target, key_file)
    kinds = {}
    for meta in result.values():
        kinds[meta["expected"]] = kinds.get(meta["expected"], 0) + 1
    print(f"wrote {len(result)} files to {target}; expected outcomes: {kinds}")

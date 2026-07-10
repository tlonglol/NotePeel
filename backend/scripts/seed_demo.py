"""Seed (or reset) the public demo account used by the "Try the demo" button.

Run against the same DB the Lambda uses:
    DATABASE_URL="<neon-pooled-url>" python -m scripts.seed_demo

Idempotent: wipes any existing demo content and re-seeds, so it doubles as a reset.
"""
from datetime import datetime

from app.database import SessionLocal
import app.models  # noqa: F401 — register all models on Base.metadata
from app.models.user import User
from app.models.note import Note, ProcessingStatus
from app.models.notebook import Notebook
from app.models.flashcard import FlashcardSet, Flashcard, AISummary, AIExplanation
from app.controllers.auth_controller import AuthController

DEMO_EMAIL = "demo@notepeel.xyz"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demodemo123"


# ── small HTML helpers so the seeded notes look like real OCR output ──────────
def h(text: str) -> str:
    return (
        f'<h2 style="font-size:1.4em;color:#FF9800;margin:18px 0 8px;'
        f'text-transform:uppercase;letter-spacing:0.05em;">{text}</h2>'
    )


def p(text: str) -> str:
    return f'<p style="margin:10px 0;line-height:1.75;">{text}</p>'


def bullets(items: list[str]) -> str:
    inner = "".join(
        '<div style="display:flex;gap:10px;margin-bottom:6px;line-height:1.75;">'
        '<span style="color:#FF9800;font-weight:bold;flex-shrink:0;">◆</span>'
        f'<span>{i}</span></div>'
        for i in items
    )
    return f'<div style="margin:12px 0;">{inner}</div>'


def build_notes() -> list[dict]:
    return [
        {
            "title": "Cell Structure",
            "subject": "Biology",
            "topic": "Cell Biology",
            "tags": "cells, organelles, eukaryote",
            "raw_text": (
                "Cell Structure. Cells are the basic structural and functional unit of all living "
                "organisms. Key organelles: Nucleus stores DNA and controls cell activities. "
                "Mitochondria are the powerhouse and produce ATP. Ribosomes synthesize proteins. "
                "Endoplasmic reticulum transports materials. Golgi apparatus packages and ships proteins. "
                "Prokaryotes have no membrane-bound nucleus; eukaryotes do."
            ),
            "structured_text": (
                h("Cell Structure")
                + p("Cells are the basic structural and functional unit of all living organisms.")
                + h("Key Organelles")
                + bullets([
                    "Nucleus — stores DNA and controls cell activities",
                    "Mitochondria — the powerhouse; produces ATP via respiration",
                    "Ribosomes — synthesize proteins",
                    "Endoplasmic reticulum — transports materials through the cell",
                    "Golgi apparatus — packages and ships proteins",
                ])
                + h("Prokaryotic vs Eukaryotic")
                + bullets([
                    "Prokaryotes — no membrane-bound nucleus (e.g. bacteria)",
                    "Eukaryotes — membrane-bound nucleus and organelles (plants, animals)",
                ])
            ),
        },
        {
            "title": "Photosynthesis",
            "subject": "Biology",
            "topic": "Plant Biology",
            "tags": "photosynthesis, chloroplast, ATP",
            "raw_text": (
                "Photosynthesis converts light energy into chemical energy stored in glucose. "
                "Overall reaction: 6CO2 + 6H2O + light -> C6H12O6 + 6O2. Two stages: "
                "light-dependent reactions in the thylakoid produce ATP and NADPH; the Calvin "
                "cycle in the stroma fixes CO2 into glucose."
            ),
            "structured_text": (
                h("Photosynthesis")
                + p("The process by which plants convert light energy into chemical energy stored in glucose.")
                + h("Overall Reaction")
                + p(r"$$6CO_2 + 6H_2O \xrightarrow{\text{light}} C_6H_{12}O_6 + 6O_2$$")
                + h("Two Stages")
                + bullets([
                    "Light-dependent reactions — occur in the thylakoid; produce ATP and NADPH",
                    "Calvin cycle — occurs in the stroma; fixes $CO_2$ into glucose",
                ])
            ),
            "summary": (
                "Photosynthesis converts light energy, CO₂, and water into glucose and oxygen. "
                "It runs in two stages: the light-dependent reactions in the thylakoid membranes "
                "(producing ATP and NADPH), and the Calvin cycle in the stroma (using that energy "
                "to fix CO₂ into glucose). Overall: 6CO₂ + 6H₂O + light → C₆H₁₂O₆ + 6O₂."
            ),
        },
        {
            "title": "Derivatives & The Chain Rule",
            "subject": "Math",
            "topic": "Calculus",
            "tags": "derivatives, chain rule, limits",
            "raw_text": (
                "The derivative measures the instantaneous rate of change of a function. "
                "Limit definition: f'(x) = lim h->0 [f(x+h) - f(x)] / h. Power rule: d/dx x^n = n x^(n-1). "
                "Product rule: (fg)' = f'g + fg'. Chain rule: d/dx f(g(x)) = f'(g(x)) g'(x)."
            ),
            "structured_text": (
                h("Derivatives")
                + p("The derivative measures the instantaneous rate of change of a function "
                    "(the slope of the tangent line).")
                + p(r"$$f'(x) = \lim_{h \to 0} \frac{f(x+h) - f(x)}{h}$$")
                + h("Common Rules")
                + bullets([
                    r"Power rule: $\frac{d}{dx} x^n = n x^{n-1}$",
                    r"Product rule: $(fg)' = f'g + fg'$",
                    r"Chain rule: $\frac{d}{dx} f(g(x)) = f'(g(x)) \cdot g'(x)$",
                ])
            ),
            "flashcards": [
                ("What does the derivative of a function represent?",
                 "The instantaneous rate of change of the function at a point — the slope of the tangent line."),
                ("State the power rule.",
                 "d/dx of x^n = n · x^(n−1)."),
                ("State the chain rule.",
                 "d/dx f(g(x)) = f'(g(x)) · g'(x)."),
                ("What is the limit definition of the derivative?",
                 "f'(x) = lim(h→0) [f(x+h) − f(x)] / h."),
            ],
        },
    ]


def main() -> None:
    db = SessionLocal()
    try:
        demo = db.query(User).filter(User.email == DEMO_EMAIL).first()

        if demo:
            # Wipe existing demo content (FK ON DELETE CASCADE handles flashcards,
            # summaries, and note_notebooks links).
            db.query(FlashcardSet).filter(FlashcardSet.owner_id == demo.id).delete(synchronize_session=False)
            db.query(AISummary).filter(AISummary.owner_id == demo.id).delete(synchronize_session=False)
            db.query(AIExplanation).filter(AIExplanation.owner_id == demo.id).delete(synchronize_session=False)
            db.query(Note).filter(Note.owner_id == demo.id).delete(synchronize_session=False)
            db.query(Notebook).filter(Notebook.owner_id == demo.id).delete(synchronize_session=False)
            demo.hashed_password = AuthController.hash_password(DEMO_PASSWORD)
            demo.is_active = True
            db.commit()
        else:
            demo = User(
                email=DEMO_EMAIL,
                username=DEMO_USERNAME,
                hashed_password=AuthController.hash_password(DEMO_PASSWORD),
                is_active=True,
            )
            db.add(demo)
            db.commit()
            db.refresh(demo)

        notebook = Notebook(name="Biology & Calculus", color="#66BB6A", owner_id=demo.id)
        db.add(notebook)
        db.flush()

        for spec in build_notes():
            note = Note(
                title=spec["title"],
                raw_text=spec["raw_text"],
                structured_text=spec["structured_text"],
                subject=spec["subject"],
                topic=spec["topic"],
                tags=spec["tags"],
                status=ProcessingStatus.COMPLETED,
                processed_at=datetime.utcnow(),
                image_filename=f"{spec['title'].lower().replace(' ', '_')}.jpg",
                owner_id=demo.id,
            )
            db.add(note)
            db.flush()
            notebook.notes.append(note)

            if spec.get("flashcards"):
                fset = FlashcardSet(note_id=note.id, owner_id=demo.id, title=f"Flashcards: {spec['title']}")
                db.add(fset)
                db.flush()
                for q, a in spec["flashcards"]:
                    db.add(Flashcard(set_id=fset.id, question=q, answer=a))

            if spec.get("summary"):
                note.ai_summary = spec["summary"]
                db.add(AISummary(note_id=note.id, owner_id=demo.id, summary=spec["summary"]))

        db.commit()
        print(f"✅ demo account seeded: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print("   1 notebook, 3 notes, 1 flashcard set, 1 summary")
    finally:
        db.close()


if __name__ == "__main__":
    main()

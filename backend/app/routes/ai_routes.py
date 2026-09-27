import json
import re
import os
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.note import Note
from app.models.flashcard import FlashcardSet, Flashcard, AISummary, AIExplanation
from app.controllers.auth_controller import get_current_user
from app.services import workers_ai
from app.config import get_settings
from app.rag.ask import ask as rag_ask, ask_stream as rag_ask_stream, sse
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/ai", tags=["AI"])


def _get_user_note(db: Session, note_id: int, user: User) -> Note:
    note = db.query(Note).filter(Note.id == note_id, Note.owner_id == user.id).first()
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if not note.raw_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Note has no text content")
    return note


# ── Flashcard Generation ──

@router.post("/flashcards/{note_id}")
async def generate_flashcards(
    note_id: int,
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    note = _get_user_note(db, note_id, current_user)

    # Check if flashcards already exist (unless regenerate=True)
    if not regenerate:
        existing = db.query(FlashcardSet).filter(
            FlashcardSet.note_id == note_id,
            FlashcardSet.owner_id == current_user.id
        ).order_by(FlashcardSet.created_at.desc()).first()
        
        if existing:
            return {
                "id": existing.id,
                "note_id": existing.note_id,
                "title": existing.title,
                "created_at": existing.created_at,
                "cards": [{"id": c.id, "question": c.question, "answer": c.answer} for c in existing.cards],
                "cached": True
            }

    try:
        cards_data = await workers_ai.generate_flashcards(note.raw_text[:4000])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

    # Delete old flashcards for this note if regenerating
    if regenerate:
        db.query(FlashcardSet).filter(
            FlashcardSet.note_id == note_id,
            FlashcardSet.owner_id == current_user.id
        ).delete()

    # Save to database
    fc_set = FlashcardSet(
        note_id=note_id,
        title=f"Flashcards for {note.title}",
        owner_id=current_user.id,
    )
    db.add(fc_set)
    db.flush()

    for card in cards_data:
        fc = Flashcard(
            set_id=fc_set.id,
            question=card.get("question", ""),
            answer=card.get("answer", ""),
        )
        db.add(fc)

    db.commit()
    db.refresh(fc_set)

    return {
        "id": fc_set.id,
        "note_id": fc_set.note_id,
        "title": fc_set.title,
        "created_at": fc_set.created_at,
        "cards": [{"id": c.id, "question": c.question, "answer": c.answer} for c in fc_set.cards],
        "cached": False
    }


@router.get("/flashcards/{note_id}")
def get_flashcards(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sets = db.query(FlashcardSet).filter(
        FlashcardSet.note_id == note_id,
        FlashcardSet.owner_id == current_user.id
    ).order_by(FlashcardSet.created_at.desc()).all()

    return [
        {
            "id": s.id,
            "note_id": s.note_id,
            "title": s.title,
            "created_at": s.created_at,
            "cards": [{"id": c.id, "question": c.question, "answer": c.answer} for c in s.cards],
        }
        for s in sets
    ]


# ── Summarize ──

@router.post("/summarize/{note_id}")
async def summarize_note(
    note_id: int,
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    note = _get_user_note(db, note_id, current_user)

    # Return cached summary if exists (unless regenerate=True)
    if not regenerate and note.ai_summary:
        return {"summary": note.ai_summary, "cached": True}

    try:
        summary = await workers_ai.summarize_note(note.raw_text[:4000])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI summarization failed: {str(e)}")

    # Cache the summary on the note
    note.ai_summary = summary
    db.commit()

    return {"summary": summary, "cached": False}


# ── Explain ──

class ExplainRequest(BaseModel):
    text: str
    note_id: int | None = None


@router.post("/explain")
async def explain_text(
    request: ExplainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="No text provided")

    text_to_explain = request.text.strip()
    
    # Check cache if note_id provided - look for exact or similar match
    if request.note_id:
        existing = db.query(AIExplanation).filter(
            AIExplanation.note_id == request.note_id,
            AIExplanation.owner_id == current_user.id,
            AIExplanation.highlighted_text == text_to_explain
        ).first()
        
        if existing:
            return {
                "explanation": existing.explanation,
                "highlighted_text": existing.highlighted_text,
                "cached": True
            }

    # Get note context if available
    context = ""
    if request.note_id:
        note = db.query(Note).filter(Note.id == request.note_id, Note.owner_id == current_user.id).first()
        if note and note.raw_text:
            context = note.raw_text[:2000]

    try:
        explanation = await workers_ai.explain_highlight(text_to_explain[:500], context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI explanation failed: {str(e)}")

    # Save to cache if note_id provided
    if request.note_id:
        ai_exp = AIExplanation(
            note_id=request.note_id,
            owner_id=current_user.id,
            highlighted_text=text_to_explain,
            explanation=explanation
        )
        db.add(ai_exp)
        db.commit()

    return {"explanation": explanation, "highlighted_text": text_to_explain, "cached": False}


@router.get("/explanations/{note_id}")
def get_explanations(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all cached explanations for a note."""
    explanations = db.query(AIExplanation).filter(
        AIExplanation.note_id == note_id,
        AIExplanation.owner_id == current_user.id
    ).order_by(AIExplanation.created_at.desc()).all()

    return [
        {
            "id": e.id,
            "highlighted_text": e.highlighted_text,
            "explanation": e.explanation,
            "created_at": e.created_at
        }
        for e in explanations
    ]


# ── Categorize ──

@router.post("/categorize/{note_id}")
async def categorize_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Auto-categorize a note by subject, topic, and tags."""
    note = _get_user_note(db, note_id, current_user)

    # Return cached if already categorized
    if note.subject and note.topic and note.tags:
        return {
            "subject": note.subject,
            "topic": note.topic,
            "tags": note.tags.split(",") if note.tags else [],
            "cached": True
        }

    try:
        result = await workers_ai.categorize_note(note.raw_text[:4000])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI categorization failed: {str(e)}")

    # Save to note
    note.subject = result.get("subject", "")
    note.topic = result.get("topic", "")
    tags = result.get("tags", [])
    note.tags = ",".join(tags) if isinstance(tags, list) else str(tags)
    db.commit()

    return {
        "subject": note.subject,
        "topic": note.topic,
        "tags": tags,
        "cached": False
    }


# ── Ask your notes (retrieval-grounded Q&A) ──

class AskRequest(BaseModel):
    question: str
    notebook_id: int | None = None
    mode: str | None = None       # override: vector | hybrid | fts (default from settings)


@router.get("/ask/config")
def ask_config():
    s = get_settings()
    return {
        "retrieval_mode": s.rag_retrieval_mode,
        "generation_model": s.rag_generation_model,
        "streaming": s.rag_streaming_enabled,
    }


# Sync handlers on purpose: retrieval and generation are blocking calls, and a
# `def` route runs in FastAPI's threadpool instead of blocking the event loop.
@router.post("/ask")
def ask_notes(
    body: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question is empty")
    if len(q) > 1000:
        raise HTTPException(status_code=400, detail="Question is too long (max 1000 characters)")
    if body.mode and body.mode not in ("vector", "hybrid", "fts"):
        raise HTTPException(status_code=400, detail="mode must be vector, hybrid or fts")
    return rag_ask(db, current_user.id, q, notebook_id=body.notebook_id, mode=body.mode).to_dict()


@router.post("/ask/stream")
def ask_notes_stream(
    body: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Server-sent events: `sources` first, then `token` deltas, then `done`.
    Streams for real under uvicorn and under the Lambda Web Adapter with
    RESPONSE_STREAM; under plain Mangum the body is buffered until the end."""
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question is empty")
    if len(q) > 1000:
        raise HTTPException(status_code=400, detail="Question is too long (max 1000 characters)")

    def gen():
        for ev in rag_ask_stream(db, current_user.id, q, notebook_id=body.notebook_id, mode=body.mode):
            yield sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

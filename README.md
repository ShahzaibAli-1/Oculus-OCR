# Ocular — Agentic OCR System

An end-to-end multi-agent document digitisation system built for PPIT (Phase 2).

Ocular uses a GPT-4o Vision **analysis agent**, an OpenCV **perception agent**, a **formatting agent**, and a **document agent** — all coordinated by an orchestrator following an Observe → Interpret → Decide → Act → Learn loop.

Upload a document image and Ocular preprocesses it, extracts text with high confidence scores, structures it intelligently, and exports a formatted Word document — with a full audit log and memory across sessions.

**Stack:** Python · OpenAI GPT-4o · OpenCV · Tesseract · Flask · SQLite

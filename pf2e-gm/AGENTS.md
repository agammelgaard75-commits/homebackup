# Project: PF2e GM Toolkit

Build a modular, locally hosted web application containing independent Game Master tools for Pathfinder Second Edition Remaster.

## Purpose

The application is intended for a beginner GM.

Its main purpose is to simplify adventure preparation, quickly reference rules, calculate game mechanics, and reduce bookkeeping during sessions.

It is not intended to replace the Pathfinder rulebooks.

## Technology

- Python 3
- FastAPI
- SQLite
- HTML/CSS/JavaScript
- pytest
- No required cloud services
- No LLM dependency during normal use

## Architecture

1. Create a master application serving as a dashboard.
2. Implement each GM tool in its own subfolder.
3. Tools must have well-defined interfaces.
4. Tools must remain independently testable.
5. Common data and utilities belong in shared modules.
6. Game mechanics must be calculated deterministically.
7. Store campaign and party information persistently.
8. Avoid unnecessary dependencies and architectural complexity.

## Rules

- Use PF2e Remaster rules as the default.
- Reference Player Core, GM Core, and Monster Core.
- Maintain a structured database of rule references.
- Include book names, page references, and official online links where available.
- Never invent rule interpretations or source references.
- Clearly distinguish house rules from official rules.
- Avoid embedding complete copyrighted rulebooks.
- Keep all rule calculations covered by automated tests.

## Development Requirements

- Every tool must have its own README.
- Every tool must have automated tests for its calculations.
- The master must be able to launch individual tools.
- Changes to one tool should not require modifications to unrelated tools.
- Preserve working functionality during development.
- Prefer simple, maintainable solutions over elaborate frameworks.

## Initial Task

Create the project directory structure, document the architecture, and implement a minimal working master dashboard.

Add placeholders for the ten planned GM tools.

Implement only the Rules Quick Reference tool initially.

Do not proceed with other tools until the first implementation has been tested and reviewed.

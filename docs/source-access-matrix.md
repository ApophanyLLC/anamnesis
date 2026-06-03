---
title: Source Access Matrix
doc_id: DOC-APP-ANAMNESIS-SOURCE-ACCESS-MATRIX-001
type: reference
status: draft
authority: informative
audience:
- maintainer
scope:
- project
- registry
verification: source-links-reviewed
stability: experimental
owner: athame
last_reviewed: '2026-06-03'
---

# Source Access Matrix

## Purpose

Record Anamnesis source-access policy for assistant history import surfaces.

## Evidence note

This document extracts durable importer guidance from a prior research note.
Product storage and export behavior changes frequently, so this page should not
be treated as a permanent vendor contract. Before promoting a source from
backlog into active discovery, verify the current vendor documentation and add
source-specific safety tests.

## Ingestion tiers

| Tier | Rule | Current examples |
|---|---|---|
| Documented local transcript stores | Auto-discovery may be appropriate when the product owns a narrow local path and the parser is covered by safety tests. | Codex `~/.codex/sessions` is active. Claude Code and Gemini CLI are candidates, but not active in this snapshot. |
| Export-first surfaces | Prefer explicit user exports over raw internal files. Raw parsing should be opt-in, narrow, and version-aware. | VS Code Copilot chat, LM Studio, Open WebUI, AnythingLLM. |
| Cloud export only | Require files supplied by the user from account export or privacy dashboard flows. Do not scan broad home-directory locations. | ChatGPT, Claude web/Desktop, Gemini Apps, Microsoft Copilot. |
| Runtime/client-dependent | Do not market the runtime itself as a conversation-history source. Import from the client that manages the chat history. | Ollama. |
| Unverified or docs-backlog only | Keep as registry backlog until a primary-source path/export format and parser tests exist. | Gemini Antigravity raw files, Grok, Sai, Qwen, Poe. |

## Current active policy

Anamnesis should use direct filesystem discovery only for narrow
product-owned local roots. In this snapshot, active direct local import covers
Codex session files and conservative VS Code Copilot workspace SQLite scanning.

Cloud account-history products should enter through explicit user-controlled
import roots under `~/Anamnesis`. A discovered export root does not authorize
content reads; the user must still run `authorize` before indexing.

VS Code Copilot deserves extra caution. VS Code documents chat session
management and JSON export, but workspace storage internals are not a stable
public parser contract. The active parser is intentionally conservative and
must remain scoped to chat/Copilot-shaped SQLite records.

Gemini Antigravity is no longer active auto-discovery in this snapshot. Treat
raw paths such as `~/.gemini/antigravity/conversations` as version-specific
until a stable source path and transcript format are verified.

Ollama should not be treated as a chat-history source by itself. Its chat API
accepts conversation history as request messages, which means the authoritative
history usually belongs to Open WebUI, LM Studio, AnythingLLM, Continue, or a
custom client.

## Source notes

| Product | Recommended access model | Anamnesis status |
|---|---|---|
| ChatGPT | User-supplied account export ZIP or extracted `conversations.json`. | Active manual import root. |
| Claude web/Desktop | User-supplied account or organization export. | Active manual import root. |
| Claude Code | Candidate for local transcript import. Verify current `~/.claude/projects` behavior before activation. | Backlog gap. |
| Codex | Direct local import from `~/.codex/sessions`; additional `history.jsonl` normalization remains backlog. | Active local source plus backlog complement. |
| Gemini Apps | User-supplied Google account export. | Active manual import root. |
| Gemini CLI | Candidate for local import from documented session surfaces; parser should prefer stable CLI/session behavior over brittle raw assumptions. | Backlog gap. |
| Gemini Antigravity | Do not auto-discover raw conversation paths until stable docs and tests exist. | Docs-backlog only. |
| GitHub Copilot in VS Code | Prefer JSON export from VS Code; raw workspace storage parsing must stay conservative. | Active conservative SQLite parser; export adapter backlog. |
| GitHub Copilot CLI | Candidate for local/session-state import once narrow filters and tests exist. | Backlog candidate. |
| Microsoft Copilot | User-supplied privacy dashboard export. | Not active. |
| LM Studio | Prefer UI chat exports such as Markdown, text, or PDF. | Backlog candidate. |
| Open WebUI | Prefer Data Controls JSON export; copied database import must remain explicit. | Backlog candidate. |
| AnythingLLM | Prefer workspace chat-log export. | Backlog gap. |
| Ollama | Ask which client produced the conversations; import from that client. | Runtime only. |

## Useful current references

- ChatGPT export: <https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data>
- Claude export: <https://support.anthropic.com/en/articles/9450526-how-can-i-export-my-claude-data>
- Gemini CLI session management: <https://geminicli.com/docs/cli/session-management/>
- VS Code Copilot chat sessions: <https://code.visualstudio.com/docs/copilot/chat/chat-sessions>
- Microsoft Copilot privacy dashboard: <https://support.microsoft.com/en-us/privacy/manage-your-copilot-activity-history-in-the-privacy-dashboard>
- Ollama chat API: <https://docs.ollama.com/api/chat>
- Open WebUI import/export: <https://docs.openwebui.com/features/chat-conversations/data-controls/import-export/>
- AnythingLLM docs home: <https://docs.useanything.com/>
- LM Studio 0.4.0 chat export note: <https://lmstudio.ai/blog/0.4.0/>

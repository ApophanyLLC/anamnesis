---
title: Anamnesis Podcast Script
type: podcast-script
status: draft
authority: informative
audience:
- producer
- maintainer
scope:
- project
- podcast-script
verification: repo-evidence-reviewed
stability: experimental
---

# Anamnesis Podcast Script

## Disclaimer

This script is AI-generated draft content. It may contain inaccuracies,
omissions, or interpretations that do not accurately represent Apophany LLC,
its products, positions, roadmap, policies, or legal commitments. Treat this
script as a production draft for human review, not as an official Apophany LLC
statement.

## Producer Note

This version is written for audio. It removes long code blocks, collapses
repetition, and keeps factual claims tied to repository evidence summarized in
the companion claim audit.

## Cold Open

**Host:**

You know the feeling. You solved something with an AI assistant two weeks ago.
Maybe it was a tricky build error. Maybe it was the shape of a product decision.
Maybe it was one sentence that finally made the whole architecture click.

And now you cannot find it.

Not because it disappeared. It is probably still somewhere on your machine, or
inside an export, or buried in a local session store. The problem is that AI
work history is fragmented. Different tools save conversations in different
ways: some as exports, some as local files, some inside app databases.

That is the problem Anamnesis is trying to solve.

Anamnesis is a local-first session archaeology app. In its current MVP, it can
inventory known AI session sources, ask for explicit authorization, index
authorized sessions into a local database, and search them from the command
line.

But there is an important warning at the front of the repo: this is an
experimental source snapshot. It is not a hardened archival security product.
That matters, because AI sessions can contain private reasoning, unpublished
work, business logic, credentials accidentally pasted into prompts, and personal
context.

So today, we are not just talking about search. We are talking about consent,
local storage, parser boundaries, and what it means for a tool to be honest
about what it can and cannot remember.

## Segment 1: The Problem

**Host:**

Let us start simply. What is Anamnesis for?

**Developer:**

Anamnesis is for finding useful AI work history after it has scattered across
tools and formats.

The repo calls this a new kind of memory loss. AI-assisted work creates real
decisions and real knowledge, but the products are usually optimized for the
next prompt, not for retrieval weeks later. You may remember the idea, but not
the tool, the date, the title, or the exact words.

The current MVP is deliberately narrow. It has a command-line workflow:
discover, authorize, index, search, privacy-audit, and revoke. It uses lexical
search over a local database. It does not yet provide semantic search, a web
interface, an IDE extension, or team knowledge bases.

That narrowness is intentional. The first job is to preserve the privacy
boundary while proving that local search over authorized session history is
useful.

**Host:**

The phrase "privacy boundary" is doing a lot of work there. What is the boundary?

**Developer:**

The core rule is: discover before reading.

Discovery is an inventory step. It reports things like path, file count, total
bytes, and first and last modified time. It does not read session content. Then
the user authorizes a specific discovered source. Only after that does indexing
parse content and put searchable chunks into the local database.

## Segment 2: Discovery Without Broad Crawling

**Host:**

When people hear "discover," they may imagine a crawler wandering across the
whole home directory. Is that what happens?

**Developer:**

No. Anamnesis uses a governed list of supported sources. That list says which
apps are in scope, where Anamnesis is allowed to look, what kinds of files are
eligible, which parser handles the source, and what the risk level is.

There is an important nuance: inside a configured source root, the code does
look recursively for eligible files. But it does not do a broad home-directory
crawl.

For active local discovery, the repo currently names Codex session files and
conservative VS Code Copilot or chat workspace storage. The important point is
that these are known app-owned locations, not arbitrary user folders.

Cloud or account-history products use a different model. ChatGPT, Claude,
Gemini, Character.AI, and Notion are treated as manual import surfaces. The user
places explicit export files in dedicated Anamnesis import folders before they
can be indexed.

**Host:**

So the friction of moving an export into a specific folder is part of the safety
model.

**Developer:**

Exactly. It makes the user's intent visible in the filesystem. The README is
explicit that cloud assistant exports are not discovered from broad locations
like the downloads folder or hidden app-history folders.

ChatGPT has one extra eligibility check. Anamnesis looks for the expected
conversation export shape, and ignores unrelated files in that import area.

That is still metadata work. Discovery can reveal that files exist, how large
they are, and when they changed. The repo does not pretend metadata is nothing.
But it confines discovery to governed roots and avoids reading conversation
content until authorization.

## Segment 3: Authorization As A Contract

**Host:**

After discovery, the user authorizes a source. What are they consenting to?

**Developer:**

They are authorizing that discovered source under the registry definition that
exists at that time.

The implementation stores an authorization record in
the local authorization manifest. That record includes the source identity, the
path, whether it is authorized, and a policy snapshot identifier.

That policy snapshot identifier is a fingerprint of the source policy: what
files are eligible, how access works, which parser owns it, what the risk level
is, and related policy fields.

When indexing runs, Anamnesis compares the authorization against the current
registry. If the old policy no longer matches, indexing skips that source and
returns a policy-drift diagnostic.

**Host:**

That prevents silent expansion of access. But can the current CLI show the user
what changed?

**Developer:**

No. That is a current limitation.

The manifest stores the hash, not a full serialized copy of the old policy. So
the current code can say, "this policy identifier no longer matches," but it
cannot render a human-readable old-versus-new diff.

The CLI is also not interactive today. It prints JSON. There is no implemented
policy-diff prompt, no approval menu, and no graceful legacy fallback mode.
Better diagnostics for skipped files, parse failures, and source policy drift
are listed in the product brief as near-term hardening work.

That distinction is important. The repo has the mechanical lock. It does not
yet have the human-facing explanation that would make reauthorization fully
informed.

## Segment 4: What Indexing Does

**Host:**

Once a source is authorized, what does indexing actually do?

**Developer:**

Indexing walks the eligible files for each authorized source and sends them to
the appropriate parser. If parsing succeeds, the source's indexed documents are
replaced in the local database. If parsing fails for a file, the service records a
skipped-file diagnostic with the path and reason, then continues where it can.

The index stores normalized sessions and chunks, then uses lexical search to
find matching text.

Long text files are split into bounded chunks before indexing. The parser tries
to split at natural boundaries, like paragraphs or sentences, before falling
back to a hard cut.

Export parsing is intentionally limited. For ChatGPT, Anamnesis reads only the
conversation data inside the export, not every file packaged alongside it.
Large exports are still loaded in a relatively simple way today, so the README
calls streaming parsers a needed future step before treating this as a
high-volume archival importer.

## Segment 5: Parser Boundaries

**Host:**

The most delicate source seems to be VS Code Copilot storage. Why?

**Developer:**

Because VS Code workspace storage is not just chat history. It is shared
application and extension state. The source access matrix says VS Code Copilot
deserves extra caution because workspace storage internals are not a stable
public parser contract.

The parser is conservative. It opens those app databases read-only. It only
considers tables whose shape looks like known chat storage.

Even after a table matches structurally, rows still have to look chat-scoped.
The parser checks for Copilot or chat markers in table names and identifiers.
If the table or row does not match, it is skipped.

If a database file is malformed or cannot be read, the parser raises a
structured parse error, and the service reports that file under skipped
diagnostics. The tests cover this behavior.

**Host:**

So the trade-off is privacy over recall.

**Developer:**

Yes. If VS Code changes its schema, the parser may stop finding sessions. That
is safer than guessing and indexing unrelated extension state, but it creates a
real utility problem: the source can go quiet.

The current code does not have persistent staleness tracking. It does not store
last-index status in the database, and search does not print a scope manifest.
That means the current MVP can be safe while still being too quiet about gaps in
what it found. The product brief already names better diagnostics as hardening
work; the architectural question is how loud those diagnostics should be.

## Segment 6: Storage, Revocation, And The Limits Of Local Safety

**Host:**

Let us talk about the local database. What should users understand before they
trust it?

**Developer:**

They should understand that it is a plaintext local database. Anamnesis
restricts file permissions on its workspace, database, and authorization
manifest. The privacy audit checks those permissions and related database
settings.

Revocation is also implemented. When a source is revoked, Anamnesis purges its
indexed chunks, rebuilds the search index, and compacts the database so
ordinary revoked index text is removed from the active local index.

But the README is careful about the limit. This is not forensic erasure. It
does not protect against filesystem snapshots, backups, disk wear-leveling,
external sync tools, or copied database files. Encryption-at-rest remains a
stronger future direction for highly sensitive archives.

That is why the repo warns users not to treat the MVP as a substitute for
encryption-at-rest, formal incident response, or validated e-discovery and
preservation systems.

## Segment 7: What The Tool Is Not Yet

**Host:**

The original idea can sound like a universal memory system. How far is the repo
from that?

**Developer:**

The repo is explicit about what is not current behavior.

It does not yet provide vector search, local embeddings, synthesis, a web UI, an
IDE extension, or team knowledge bases. Local embeddings and vector storage are
described as the next implementation layer, not an implemented feature.

It also does not yet have interactive consent diffing, persistent search-time
staleness banners, or streaming parsers for very large exports. Those are
reasonable roadmap topics, but they should not be described as current
capabilities.

The current promise is smaller and more concrete: Anamnesis treats the user's
past AI work as a local archive, asks before reading it, indexes only authorized
sources, and makes the recoverable parts searchable without making cloud sync a
hidden requirement.

## Closing

**Host:**

What should builders take away from Anamnesis, even if they never use this tool?

**Developer:**

The lesson is that privacy-first tools need two kinds of integrity.

The first is access integrity: do not read what the user did not authorize. In
Anamnesis, that shows up as governed source definitions, manual import roots,
authorization records, parser ownership, policy snapshot identifiers, and local
file permissions.

The second is operational integrity: do not pretend the archive is complete
when parsers skipped files, a policy drifted, or a source went quiet. The
current MVP is stronger on the first than the second. That is an honest
statement, and it is the right foundation for hardening.

For sensitive data, silence is not always respect. Sometimes silence protects
privacy. Sometimes it hides failure. A trustworthy local tool has to know the
difference.

**Host:**

That is the real story here.

Anamnesis is not a finished fortress. It is an experimental, local-first tool
with a clear privacy boundary and a candid list of limits. It can help you
search the parts of your AI work history you explicitly authorize. It also
shows how hard it is to build memory tools that are both useful and careful.

If you are building software around private data, the challenge is not just to
lock the door. It is to tell the user, clearly and locally, what the tool knows,
what it skipped, and where its confidence ends.

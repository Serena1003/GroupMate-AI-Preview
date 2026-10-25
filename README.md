# GroupMate AI · IBSS Classroom Preview

Password-free, interactive public preview for teacher review.

**Preview:** https://Serena1003.github.io/GroupMate-AI-Preview/

## Try it

Open the page without a password. Explore the completed synthetic classroom, or select **Start a fresh guided demo**.

- **Teacher studio:** select teaching materials through four source routes, use synthetic examples, add local files or paste excerpts, apply selected references/text to the draft, then edit goals, roles, questions and selected dimensions; confirm and publish the activity.
- **Student experience:** save a goal and strategy, contribute, invite a clearly labelled preset role, submit a proposal and record confirmation, reflect, view published feedback and save a next action.
- **Class overview / Group insights / Evidence review:** inspect original source text and separate preset assessment baseline from teacher adoption.
- **Teaching feedback:** edit personal/group/six-section teacher reports, save a new draft, then publish separately. Previous versions remain in publication history.
- **中文操作说明:** Chinese walkthrough and distinction between the preview and real engine.

All preview records are **synthetic**. AI replies are preset and assessments/reports are demonstrative templates, **not live XIPU calls or measures of a visitor's ability**. No total, average or rank is computed. N/O is distinct from a low rating.

## Storage and boundaries

Changes are stored only in this browser's localStorage. Same-origin tabs in one browser share preview changes; different users or devices do not. No account authentication, backend service, real document extraction or multi-user classroom server runs on GitHub Pages. Do not put real student records or sensitive material here. No XIPU API keys are bundled. The real backend's teacher access is unchanged.

## Source

`index.html`, `preview.css` and `preview.js` contain the complete static preview source.

`engine/` contains the browsable Python engine, original classroom UI, workflow prompts, core tests and selected documentation. `groupmate-engine-source.zip` also provides the same fixed local source snapshot as one download. It excludes `.env`, classroom databases, browser sessions, private evidence, supplied books/course PDFs and Git history. Extract it locally, set your own `GROUPMATE_OWNER_SECRET`, then run:

```sh
python3 -m groupmate.server --port 8765
```

The engine and its native XIPU workflows have been exercised in synthetic local demonstrations using an operator-mediated copy/paste bridge. Official API calls are separately gated by platform API-service enablement/approval; public preview deployment does not resolve that approval.

## Design credit

The purple classroom/dashboard design was informed by the collaborator's public GroupMate UI prototypes:
https://github.com/Sivan-Bu/GroupMate-AI_Dashboard

This repository is the public demonstration preview, separate from the collaborator's repository. No license grant beyond existing source rights is implied; review permissions before reuse or distribution.

## Teaching-material selection

In **Teacher studio → Select teaching materials**, choose the case source route (existing textbook case, teacher-provided material, new textbook-based case, or web reference). Add a built-in synthetic example, select local files, or paste an authorised excerpt with a source reference. Select up to five materials and explicitly apply their references or original text to the activity draft. Changes reset the nine confirmation items.

TXT, MD and CSV contents are read locally and persisted as text in this browser. PDF, Word and PowerPoint files can be selected and labelled, but their contents are **not automatically extracted** in this static preview: paste the required excerpt. PDF files may be opened locally for viewing while their file bytes remain available in the current session; refresh retains metadata, not the original binary. The actual engine supports PDF selected-page extraction and DOCX extraction; PowerPoint extraction is not claimed. No selected teaching file is uploaded to GitHub, XIPU or any server.

## Extended browser-local interaction simulator

Use **Guided walkthrough** to fill the six stages one by one, or run a complete explicitly scripted demonstration. A new guided classroom archives the current source records before replacing the active working state.

Additional local interactions:

- A real browser-local countdown with start, pause/resume and freeze controls; no cross-device room is implied.
- Switch or add demo personas with separate goal/strategy/reflection/next-action fields.
- Maya/Ethan follow-ups selected from clearly labelled local response recipes using the latest contribution. No language model or semantic evaluation is claimed.
- Preview and accept/reject a local design recipe for one requested field; protected activity fields are not overwritten.
- Save a future event to the draft, reconfirm it and release it during the next activity; teacher support is recorded separately from student evidence.
- Versioned proposals with agreements and explained reservations; original submissions stay distinct from report synthesis.
- Open exact source excerpts with neighbouring context. Record observation limitations; incomplete data and lack of opportunity are distinct from low performance.
- Separate preset assessment baseline and teacher adoption; dependent reports become stale after adoption/condition changes.
- Revise feedback as a new draft, then publish separately; reflection still gates the current persona's personal feedback.
- Optional practice is stored separately and does not regrade the original activity.
- **Local records** shows up to five archived snapshots and a local audit trail, with JSON export/import. Imported running timers resume paused. No binary teaching files are included in JSON exports.

The static preview source is `index.html`, `preview.css`, `preview.js` and `interactions.js`. These simulation controls do not change the real Python engine, enable XIPU API service or bypass platform approval.

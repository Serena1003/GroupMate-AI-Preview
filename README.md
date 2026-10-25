# GroupMate AI · IBSS Classroom Preview

Password-free, interactive public preview for teacher review.

**Preview:** https://Serena1003.github.io/GroupMate-AI-Preview/

## Try it

Open the page without a password. Explore the completed synthetic classroom, or select **Start a fresh guided demo**.

- **Teacher studio:** edit goals, case, roles, questions, selected dimensions and classroom settings; confirm and publish the activity.
- **Student experience:** save a goal and strategy, contribute, invite a clearly labelled preset role, submit a proposal and record confirmation, reflect, view published feedback and save a next action.
- **Class overview / Group insights / Evidence review:** inspect original source text and separate preset assessment baseline from teacher adoption.
- **Teaching feedback:** edit personal/group/six-section teacher reports, save a new draft, then publish separately. Previous versions remain in publication history.
- **中文操作说明:** Chinese walkthrough and distinction between the preview and real engine.

All preview records are **synthetic**. AI replies are preset and assessments/reports are demonstrative templates, **not live XIPU calls or measures of a visitor's ability**. No total, average or rank is computed. N/O is distinct from a low rating.

## Storage and boundaries

Changes are stored only in this browser's localStorage. Same-origin tabs in one browser share preview changes; different users or devices do not. No account authentication, backend service, real document extraction or multi-user classroom server runs on GitHub Pages. Do not put real student records or sensitive material here. No XIPU API keys are bundled. The real backend's teacher access is unchanged.

## Source

`index.html`, `preview.css` and `preview.js` contain the complete static preview source.

`groupmate-engine-source.zip` contains the fixed local Python engine source snapshot, supporting UI, prompts, core tests and selected documentation. It excludes `.env`, classroom databases, browser sessions, private evidence, supplied books/course PDFs and Git history. Extract it locally, set your own `GROUPMATE_OWNER_SECRET`, then run:

```sh
python3 -m groupmate.server --port 8765
```

The engine and its native XIPU workflows have been exercised in synthetic local demonstrations using an operator-mediated copy/paste bridge. Official API calls are separately gated by platform API-service enablement/approval; public preview deployment does not resolve that approval.

## Design credit

The purple classroom/dashboard design was informed by the collaborator's public GroupMate UI prototypes:
https://github.com/Sivan-Bu/GroupMate-AI_Dashboard

This repository is the public demonstration preview, separate from the collaborator's repository. No license grant beyond existing source rights is implied; review permissions before reuse or distribution.

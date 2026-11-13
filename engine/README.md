# GroupMate Classroom

English classroom dashboard and Python engine for an IBSS discussion cycle:
teacher preparation and publication → students join and discuss → individual
reflection → teacher-reviewed group feedback → student outcome view.

## Run locally

Python 3.10 or later is recommended. The engine uses the Python standard library.
PDF extraction additionally uses Poppler `pdftotext`.

```sh
export GROUPMATE_OWNER_SECRET='choose-a-long-random-teacher-password'
python3 -m groupmate.server --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`; the teacher overview is `/teacher`.
To call the existing XIPU workflow, set `GROUPMATE_XIPU_WORKFLOW_KEY` on the
server. `.env.example` contains variable names only. Never commit live keys.

## Deploy

See [single-server deployment](deploy/README.md). The production checkout lives
in `/opt/groupmate/app`, secrets in `/etc/groupmate/groupmate.env`, and runtime
classroom data in `/var/lib/groupmate`. Source updates use a read-only GitHub
deploy key on the server and `sudo bash deploy/update.sh`.

## Core verification

```sh
python3 -m unittest discover -s tests -p test_automation.py -v
```

`groupmate/` contains the engine, `static/` the UI, `native/` the XIPU role and
workflow source assets, and `deploy/` the Nginx and systemd configuration.
Historical classroom records, teacher uploads and local credentials are not
part of this repository. The cloud deployment starts with an empty classroom.

## Browse the source

This public snapshot corresponds to engine revision `013a396`.

| Directory | Contents |
| --- | --- |
| [static/](static/) | Teacher dashboard and student classroom pages |
| [groupmate/](groupmate/) | Python HTTP server, classroom state, and XIPU integration |
| [tests/](tests/) | Engine and classroom workflow tests |
| [native/](native/) | XIPU prompts and workflow scripts |
| [deploy/](deploy/) | Server installation and deployment templates |
| [docs/](docs/) | Implementation notes |

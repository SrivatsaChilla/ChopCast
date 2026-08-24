# ADR-0006: The data directory must not live under a cloud-sync folder

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

The project repository is at `C:\Users\HP\OneDrive\Documents\workspace\...`. OneDrive is a cloud-sync client. SQLite + cloud-sync clients (OneDrive, Dropbox, iCloud Drive, Google Drive) interact badly: the sync client may lock the file mid-write, or upload a partial file, or replace the local file with a stale version. The result is `database is locked` errors, silent corruption, or the loss of recent writes.

The collector is meant to run continuously for weeks. During that time, it will write to `pireps.db` on every cycle. If OneDrive locks the file or uploads a partial copy, the collector's next cycle will fail or, worse, succeed against a corrupted file.

This is not a theoretical concern. It is a documented issue with SQLite under sync clients, and it has been observed by users of every major sync client. The SQLite manual explicitly recommends against running SQLite on network filesystems without a WAL and even then with caution.

## Decision

The default data directory is **not** under the repository. The default in `configs/default.yaml` resolves `paths.raw_db` to `${paths.root}/data/raw/pireps.db`, but `paths.root` is overridden at runtime for any deployment that lives under a sync folder.

The recommended layout is:

```
C:\Users\HP\OneDrive\Documents\workspace\...\ChopCast\        # code, git-tracked
C:\Users\HP\AppData\Local\ChopCast\data\                      # data, NOT synced
C:\Users\HP\AppData\Local\ChopCast\models\                    # models, NOT synced
```

A `.gitignore` rule covers `data/` and `models/registry/` (the local-only files). The backup destination in `database.backup.destination` is also a non-synced path, with an off-host copy scheduled separately.

The `.env.example` documents this and provides a template:

```ini
CHOPCAST_PATHS__ROOT=C:/Users/HP/AppData/Local/ChopCast
```

If the user wants to keep the data directory inside the repo (e.g., on a Linux machine without OneDrive), the default `paths.root = "."` is fine. The override is only necessary when the active profile is one where the repository is under a sync folder.

## Consequences

**Positive**

- The collector is safe to leave running. There is no risk of the sync client interrupting a write.
- Data lives outside the cloud-sync boundary, which is where operational data should be. Source code is in the cloud; data is on the local disk and is backed up separately.
- The repo can be cloned anywhere without dragging data with it.

**Negative**

- New contributors may miss the override and run the collector under the synced path, encountering corruption. We mitigate with a startup check: if `paths.root` resolves to a directory under a known sync folder (OneDrive, Dropbox, iCloud, Google Drive), the collector warns at startup and asks for confirmation.
- The data directory is now separate from the code, which means `git status` does not show its size. We mitigate with a `chopcast paths` command that prints the size of each directory.

**Mitigations**

- The startup check is implemented in `chopcast.config.Settings` and is logged at WARNING. It does not block the collector from starting, but it makes the issue visible.
- The backup script (`scripts/backup.ps1`) verifies that the backup destination is not on the same drive as the data directory, to avoid the case where a drive failure takes both.

## Alternatives considered

**Disable OneDrive sync for the repository directory.** Rejected: OneDrive's per-folder exclusion is a per-user setting. The repository may be cloned by a different user, on a different machine, without that setting. Encoding the assumption in the configuration makes the system self-describing.

**Switch to PostgreSQL.** Rejected: the data volume is small, the operational story is simpler with SQLite, and the sync issue is the only reason to consider a network database. PostgreSQL would be the right choice at scale, but we are not at scale.

**Use a Docker volume.** Rejected: requires Docker to be running at all times and is heavier than the project warrants. The override is one env var.

**Trust the WAL mode.** Rejected: WAL mode is necessary but not sufficient. The sync client can still lock the file or upload a partial copy. WAL is one defense; the directory choice is the other.

## References

- `docs/DATA_ENGINEERING.md` §8
- `docs/CONFIGURATION.md` §3 (path overrides)
- `CLAUDE.md` (the project-specific pitfall section)

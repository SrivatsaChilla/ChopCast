# Deploying the ChopCast collector to AWS EC2

You run every step here yourself. Each one says **why** it exists, what to type, and
how to tell it worked. Where a step is a habit worth keeping, it says so.

## Why this needs a server at all

The AWC cache is a **rolling ~90-minute window** — measured, not assumed. If the
collector is down for two hours, those reports are gone permanently; there is no
backfill endpoint. A laptop that sleeps (this one sleeps after 1 minute on battery)
loses data every time you close the lid.

Rough cost: **~$6–8/month** for a `t4g.micro` on demand, likely $0 while intro
credits last. Storage is negligible — the DB compresses about 9.5:1, so backups run
around 210 MB/month.

---

## Step 0 — Budget alarm, BEFORE anything else

Do this first, every time, on every cloud account you ever make.

1. Console → **Billing and Cost Management** → **Budgets** → *Create budget*
2. Template: **Zero spend budget** (alerts at the first cent), or a **$5 monthly cost
   budget**
3. Enter your email → Create

**Why first:** the failure mode for students is a forgotten resource billing quietly
for months. An alarm you set before launching anything cannot be forgotten later.

✅ *Confirm:* a budget is listed, and a confirmation email arrives.

---

## Step 1 — Stop using the root user

1. Console → **IAM** → *Users* → **Create user** → name `chopcast-admin`
2. Check *Provide user access to the AWS Management Console*
3. Attach policy **AdministratorAccess** directly
4. Create, then **save the sign-in URL and password**
5. Sign out of root. Sign back in as `chopcast-admin`
6. IAM → your user → *Security credentials* → **enable MFA** (phone authenticator)

**Why:** the root user can close the account and cannot be restricted. Real practice
is that root is used once, secured, and never touched again. This is also a standard
interview question.

✅ *Confirm:* top-right of the console shows `chopcast-admin`, not "root".

---

## Step 2 — Key pair

EC2 → *Network & Security* → **Key Pairs** → Create.
Name `chopcast-key`, type **ED25519**, format **.pem**.

It downloads once. Then:

```bash
mkdir -p ~/.ssh
mv ~/Downloads/chopcast-key.pem ~/.ssh/
chmod 400 ~/.ssh/chopcast-key.pem
```

**Why `chmod 400`:** SSH refuses a key others can read. Skipping this produces a
confusing "UNPROTECTED PRIVATE KEY FILE" error later.

✅ *Confirm:* `ls -l ~/.ssh/chopcast-key.pem` shows `-r--------`.

---

## Step 3 — Launch the instance

EC2 → **Launch instance**:

| Field | Value | Why |
|---|---|---|
| Name | `chopcast-collector` | |
| AMI | **Amazon Linux 2023** | `dnf`, systemd, SSM agent preinstalled |
| Architecture | **64-bit (Arm)** | Graviton is cheaper; pandas ships ARM wheels |
| Instance type | **t4g.micro** | Plenty for a 10-minute poll of an 85 KB file |
| Key pair | `chopcast-key` | |
| Network → Firewall | Create SG, **SSH from My IP** | Never `0.0.0.0/0` — port 22 open to the world is scanned within minutes |
| Storage | **20 GiB gp3** | ~2 GB/month growth; months of headroom |

Check the **Free tier** notice on this screen. AWS changed free-tier terms recently,
so read what it actually says rather than trusting a blog post.

✅ *Confirm:* instance state **Running**, status checks **2/2 passed** (~60s).

---

## Step 4 — Connect

```bash
ssh -i ~/.ssh/chopcast-key.pem ec2-user@<PUBLIC_IP>
```

If it hangs, your security group has the wrong IP. **Your IP changes** when you move
between campus, home, and coffee shops — come back to EC2 → Security Groups → *Edit
inbound rules* → **My IP** to refresh it.

✅ *Confirm:* the Amazon Linux banner and an `[ec2-user@ip-... ~]$` prompt.

---

## Step 5 — Bootstrap

```bash
git clone https://github.com/SrivatsaChilla/ChopCast.git
cd ChopCast
bash deploy/bootstrap.sh
```

Installs Python/git/sqlite, builds a venv from `requirements.txt`, runs **one test
pull** before enabling anything, then installs and starts the systemd service.

✅ *Confirm:* the script ends with `done.` and prints a `seen=… new=… dup=…` line.

---

## Step 6 — Verify it is actually collecting

```bash
systemctl status chopcast          # expect: active (running)
journalctl -u chopcast -f          # watch a live poll; Ctrl-C to stop watching
```

Wait ~10 minutes for a second poll, then:

```bash
cd ~/ChopCast
./venv/bin/python collector.py --health   # expect: HEALTHY, exit 0
./venv/bin/python collector.py --stats
```

**The number that proves correctness** is not `new=` — it is `dup=`. A large `dup=`
means deduplication is working against the rolling snapshot. If `dup=0` on a second
poll, every report is being stored twice and the dataset is being corrupted; stop and
investigate before letting it run.

---

## Step 7 — Seed with the data already collected

There are ~2,600 real reports on the laptop already. From your **Mac**:

```bash
scp -i ~/.ssh/chopcast-key.pem ~/Desktop/ChopCast/pireps.db ec2-user@<PUBLIC_IP>:~/ChopCast/pireps.db.seed
```

Then on the **instance**:

```bash
cd ~/ChopCast
sudo systemctl stop chopcast
sqlite3 pireps.db "ATTACH 'pireps.db.seed' AS s; INSERT OR IGNORE INTO reports SELECT * FROM s.reports;"
sudo systemctl start chopcast
./venv/bin/python collector.py --stats
```

`INSERT OR IGNORE` plus the content hash makes this safe — overlapping reports collapse
automatically. Stopping the service first avoids two writers on one SQLite file.

> **From this moment the EC2 copy is authoritative.** The laptop's `pireps.db` is a
> stale scratch copy. Do not merge it back later — pull fresh from S3 instead.

---

## Step 8 — Reboot test (the actual requirement)

```bash
sudo reboot
# wait ~40s, reconnect
ssh -i ~/.ssh/chopcast-key.pem ec2-user@<PUBLIC_IP>
systemctl status chopcast
cd ~/ChopCast && ./venv/bin/python collector.py --health
```

✅ *Confirm:* the service came back **without you starting it**, and `--stats` shows no
duplicated rows across the restart. That is what `WantedBy=multi-user.target` buys you:
start on boot, no login required.

---

## Step 9 — Backups to S3

A single EBS volume is one accident away from losing weeks of irreplaceable data.

**Bucket:** S3 → Create bucket → `chopcast-backups-<yourname>` (globally unique),
defaults are fine (private, encrypted).

**Instance role** — so the box can write to S3 without any stored keys:

1. IAM → Roles → **Create role** → AWS service → **EC2**
2. Permissions: **AmazonS3FullAccess** *(tighten to just this bucket once it works)*
3. Name `chopcast-ec2-role`
4. EC2 → select instance → *Actions → Security → Modify IAM role* → attach it

**Why a role, not access keys:** roles hand out short-lived rotating credentials. A
long-lived key pasted into a file is the single most common way cloud accounts get
compromised.

**Enable the timer:**

```bash
cd ~/ChopCast
echo 'export CHOPCAST_BUCKET=chopcast-backups-<yourname>' >> ~/.bashrc && source ~/.bashrc
sudo systemctl enable --now chopcast-backup.timer
sudo systemctl start chopcast-backup.service     # run once now, don't wait for midnight
aws s3 ls s3://$CHOPCAST_BUCKET/
```

✅ *Confirm:* `pireps-latest.db.gz` and a timestamped copy are listed.

`backup.sh` uses `sqlite3 .backup` rather than `cp`, because copying a file that is
being written can capture a torn page. It also refuses to upload a snapshot with zero
rows — a corrupt backup that uploads cleanly is worse than one that fails loudly.

---

## Step 10 — Getting data back for modeling

```bash
aws s3 cp s3://chopcast-backups-<yourname>/pireps-latest.db.gz .
gunzip pireps-latest.db.gz
sqlite3 pireps-latest.db "SELECT COUNT(*) FROM reports WHERE report_type LIKE '%PIREP%' AND turbulence IS NOT NULL;"
```

Pull from S3 rather than scp-ing off the running box: it never interrupts collection,
and it forces the backup path to stay working.

---

## Operating it

| Task | Command |
|---|---|
| Is it alive? | `./venv/bin/python collector.py --health` |
| How much data? | `./venv/bin/python collector.py --stats` |
| Recent logs | `journalctl -u chopcast -n 50` |
| Restart | `sudo systemctl restart chopcast` |
| Deploy new code | `git pull && sudo systemctl restart chopcast` |
| Disk space | `df -h /` |

**Check `--health` every few days.** With a 90-minute window, a stall you notice a week
late is a week of data you cannot get back.

### If it stops collecting

1. `systemctl status chopcast` — crashed, or never started?
2. `journalctl -u chopcast -n 100` — the traceback will be here
3. `df -h /` — a full disk stops SQLite writes
4. `curl -sI https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz | head -1`
   — is AWC itself up?

### Shutting down

Stopping the instance halts billing for compute but **not** for the EBS volume. To stop
paying entirely, back up to S3 first, then terminate the instance and delete the volume.

# Configuration

> Authoritative for `configs/` and `.env`. Configuration is layered: defaults → profile → environment. Code never reads environment variables directly; it reads `Settings`.

---

## 1. The rule

> **No string literal for behavior inside `chopcast/*`.**

URLs, paths, thresholds, model names, regex patterns, label rules, retry counts — all of it lives in a typed config object loaded at startup. The only strings that appear in `chopcast/` are type names, log messages, and exception messages.

This rule is enforced by code review. There is no automated check for it, because detecting "behavior strings" precisely is hard. The architectural intent is what matters.

---

## 2. Layers

Configuration is composed from three sources, in this order. Later sources override earlier ones.

1. **Defaults** in `configs/default.yaml`.
2. **Profile overlay** in `configs/{profile}.yaml` (e.g., `dev`, `prod`, `ci`).
3. **Environment** in `.env` and the process environment.

The active profile is selected by the `CHOPCAST_PROFILE` env var. If unset, the default profile is used.

```
chopcast/config.py
    Settings.load("dev")
        loads configs/default.yaml
        overlays configs/dev.yaml
        overlays .env
        overlays os.environ
        returns frozen Settings
```

`Settings` is a Pydantic `BaseModel`. Validation runs once at load time. A bad value (`POLL_SECONDS=-1`, a malformed URL, a missing required key) raises `ConfigError` at startup, not at first use.

---

## 3. Schema

The full configuration schema is mirrored by a single `Settings` model. Each section corresponds to one YAML file.

### 3.1 `configs/default.yaml`

```yaml
# All values shown are defaults.

paths:
  root: "."                       # resolved to absolute at load time
  raw_db: "${paths.root}/data/raw/pireps.db"
  raw_dir: "${paths.root}/data/raw"
  processed_dir: "${paths.root}/data/processed"
  features_dir: "${paths.root}/data/features"
  models_dir: "${paths.root}/models/registry"
  registry_db: "${paths.root}/models/registry/registry.db"
  runs_dir: "${paths.root}/runs"
  logs_dir: "${paths.root}/logs"

collector:
  source_url: "https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz"
  user_agent: "chopcast/0.1 (+contact@example.com)"
  poll_seconds: 600
  request_timeout_seconds: 60
  max_retries: 5
  max_backoff_seconds: 300
  backoff_base_seconds: 5
  validation:
    lat_range: [-90.0, 90.0]
    lon_range: [-180.0, 180.0]
    require_raw_text: true
    require_obs_time: false
  dedup:
    lat_decimals: 4
    lon_decimals: 4

database:
  journal_mode: "WAL"
  foreign_keys: true
  busy_timeout_ms: 5000
  backup:
    enabled: true
    schedule: "03:00"             # local time
    retention_days: 30
    destination: "${paths.root}/backups"

processing:
  parser_version: "v1"
  labeler_version: "v1"
  cleaner_version: "v1"
  feature_builder_version: "v1"
  cleaner:
    strip_fields: ["/TB"]
    drop_tb_block: true
    lowercase: true
    collapse_whitespace: true
    preserve_remarks_tb_mentions: true
  features:
    altitude_bands: [[0, 20000], [20000, 30000], [30000, 40000], [40000, 60000]]
    aircraft_unknown_token: "<UNK>"
    use_hour_of_day: true
    use_day_of_year: true

labeling:
  rules_path: "${paths.root}/configs/labeling.yaml"
  default_label: "None"

text:
  stop_words_path: "${paths.root}/configs/stop_words.txt"
  tfidf:
    ngram_range: [1, 2]
    min_df: 5
    max_df: 0.95
    sublinear_tf: true
  transformer:
    model_name: "distilbert-base-uncased"
    max_length: 128
    truncation: "head_tail"

training:
  default_split:
    mode: "stratified"            # stratified | time | spatiotemporal
    test_size: 0.2
    seed: 42
  baseline:
    kind: "logreg"                # logreg | linear_svc
    class_weight: "balanced"
    max_iter: 1000
    C: 1.0
  transformer:
    epochs: 3
    batch_size: 16
    learning_rate: 5.0e-5
    warmup_steps: 100
    fp16: false
  imbalance:
    strategy: "class_weight"      # class_weight | smote | none
  regression_gate:
    macro_f1_tolerance: 0.005
    per_class_f1_tolerance: 0.01

evaluation:
  classes: ["None", "Light", "Moderate", "Severe"]
  slice_columns: ["altitude_band", "report_type", "aircraft_type"]

weather:
  enabled: false                  # toggled at M6
  provider: "metar"
  metar:
    source_url: "https://aviationweather.gov/api/data/metar"
    max_distance_km: 50
    max_time_delta_minutes: 60
  cache:
    path: "${paths.root}/data/weather/metar.parquet"
    retention_days: 30

api:
  host: "0.0.0.0"
  port: 8000
  log_level: "info"
  request_body_log: false         # NEVER enable in prod
  include_disclaimer_header: true

monitoring:
  prometheus:
    enabled: true
    path: "/metrics"
  drift:
    enabled: true
    method: "psi"                 # psi | ks
    threshold: 0.2
    window_size: 1000

logging:
  level: "INFO"
  format: "json"                  # json | console
  destination: "stdout"           # stdout | file | both
  file_path: "${paths.logs_dir}/chopcast.log"
  rotate_max_bytes: 10485760
  rotate_backup_count: 5
```

### 3.2 Profile overlays

`configs/dev.yaml` might override:

```yaml
logging:
  level: "DEBUG"
  format: "console"
database:
  journal_mode: "TRUNCATE"        # not WAL during dev
api:
  port: 8001
```

`configs/prod.yaml`:

```yaml
logging:
  level: "INFO"
  format: "json"
  destination: "both"
api:
  log_level: "warning"
  include_disclaimer_header: true
monitoring:
  drift:
    enabled: true
```

`configs/ci.yaml`:

```yaml
paths:
  root: "/tmp/chopcast-ci"
logging:
  level: "WARNING"
```

### 3.3 `.env`

Secrets and machine-specific values go in `.env`. The file is gitignored. A template lives at `.env.example`.

```ini
# .env.example
CHOPCAST_PROFILE=dev

# AWC requires a User-Agent that identifies the operator.
# Format: "<app>/<version> (+<contact>)"
CHOPCAST_COLLECTOR__USER_AGENT="chopcast/0.1 (+your-email@example.com)"

# Optional overrides (uncomment to use)
# CHOPCAST_COLLECTOR__POLL_SECONDS=300
# CHOPCAST_API__PORT=8001
# CHOPCAST_LOGGING__LEVEL=DEBUG
```

**Naming convention:** double-underscore (`__`) represents nesting. `CHOPCAST_COLLECTOR__POLL_SECONDS=300` overrides `collector.poll_seconds` in the active profile.

`.env` is loaded once at startup. It is *not* reloaded during a long-running process. To pick up changes, restart the process.

---

## 4. Component-specific configs

Several components have their own YAML because their values are large or change independently of the rest.

### 4.1 `configs/labeling.yaml`

```yaml
version: v1
none:
  - "NEG"
  - "TB NIL"
  - "SMOOTH"
light:
  - "LGT"
  - "LGT CHOP"
moderate:
  - "MOD"
  - "LGT-MOD"
  - "OCNL MOD"
  - "MOD CHOP"
severe:
  - "SEV"
  - "MOD-SEV"
  - "EXTRM"
  - "SEV CHOP"
combination_strategy: max
chop_only_label: light
unknown_strategy: none   # what to assign to an unrecognized value
```

The rules are loaded into `LabelingRules` at startup. Changing the rules is a content-breaking change that requires a new feature store version.

### 4.2 `configs/stop_words.txt`

One stop word per line. Comments with `#`. Empty lines ignored. Applied by the TF-IDF vectorizer.

```
# aviation stop words that add no signal
a
the
of
at
in
on
for
to
and
or
is
was
were
are
be
been
being
```

### 4.3 Model configs

Each model kind has its own config block in `default.yaml`. There are no per-experiment YAML files in `configs/`. Experiment-specific overrides are passed on the CLI:

```bash
chopcast-train run --config configs/default.yaml \
  --override training.baseline.C=0.5 \
  --override training.baseline.class_weight=balanced_subsample
```

This keeps the experiment record in the run manifest rather than in scattered YAML files.

---

## 5. Weather provider configuration

M6 introduces weather providers. The first provider is METAR. Future providers (NEXRAD, model-derived gridded products) follow the same shape.

```yaml
weather:
  enabled: true
  provider: "metar"
  metar:
    source_url: "https://aviationweather.gov/api/data/metar"
    max_distance_km: 50
    max_time_delta_minutes: 60
    rate_limit_per_minute: 60
  cache:
    path: "${paths.root}/data/weather/metar.parquet"
    retention_days: 30
```

The provider's URL and rate limit are config, not constants. A future addition of a `nexrad` block is purely additive.

---

## 6. Secrets

| Source | Example | How to set |
|---|---|---|
| `.env` | `CHOPCAST_COLLECTOR__USER_AGENT` | Edit the local file |
| Process env | Same | `export` in the shell |
| Secret manager (M7) | Vault, AWS Secrets Manager | `chopcast-secrets fetch` at startup |

The collector's `User-Agent` is the only "secret" we have today. It is not actually secret (it's identifying, not authenticating), but we keep it in `.env` so that:

1. AWC sees a stable identifier per machine.
2. A typo fails at startup, not at the first HTTP request.

When M6 adds METAR or other rate-limited sources, the relevant keys go into `.env`. When M7 adds a real secrets manager, the config layer abstracts it: the application sees `settings.weather.metar.api_key`; the loader knows whether to read from `.env` or to call Vault.

---

## 7. Validation

`Settings` is a Pydantic model. Every field is typed. Validation runs once at startup.

| Field | Validation |
|---|---|
| `collector.poll_seconds` | `int > 0` |
| `collector.validation.lat_range` | length 2, increasing, within [-90, 90] |
| `processing.cleaner.strip_fields` | non-empty tuple of strings starting with `/` |
| `training.baseline.C` | `float > 0` |
| `weather.metar.max_distance_km` | `float > 0` (when weather.enabled) |
| `logging.level` | one of `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `paths.*` | existing or creatable directory |

A validation error raises `ConfigError` with the field path and reason. The CLI prints a one-line summary and exits non-zero.

---

## 8. Operational commands

```bash
# show the effective config for the active profile
chopcast config show

# show a single section
chopcast config show --section collector

# validate the config without running anything
chopcast config validate

# print the resolved paths
chopcast paths
```

`chopcast config show` prints the config as YAML with all environment overlays applied. This is the first thing to check when something "works on my machine" but fails elsewhere.

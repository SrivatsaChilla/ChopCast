# Turbulence From Text Requirements Specification

## 1. Purpose

This document defines the initial requirements for the Turbulence From Text
project. It is meant to be revised as the project idea sharpens, real data is
inspected, and technical constraints become clearer.

The project builds an aviation machine learning pipeline that collects pilot
reports, classifies turbulence severity from report text, visualizes turbulence
geospatially, and investigates relationships between turbulence reports and
weather conditions.

## 2. Project Summary

Pilots submit PIREPs, or pilot reports, that describe flight conditions using
short aviation phrases. Some reports include turbulence information in structured
fields such as `/TB LGT`, `/TB MOD`, or `/TB SEV`.

The project uses those structured turbulence fields as labels, removes them from
the model input to avoid label leakage, and trains a classifier to predict
turbulence severity from the remaining report text and optional contextual
features.

The broader system should support three linked outcomes:

- classify turbulence severity from cleaned PIREP text
- display reports and predictions on a geospatial map
- enrich reports with weather observations to explore atmospheric drivers of
  turbulence

## 3. Goals

### 3.1 Primary Goals

- Build a reliable data collection pipeline for recent aircraft reports.
- Create a clean labeled dataset for turbulence severity classification.
- Train and evaluate a baseline text classifier.
- Visualize PIREPs and predictions by location, altitude, time, and severity.
- Explore whether nearby weather conditions improve classification or explain
  turbulence patterns.

### 3.2 Learning Goals

- Teach practical data collection from a public operational data source.
- Practice defensive parsing and schema discovery.
- Demonstrate leakage-safe machine learning workflow.
- Compare simple ML baselines against more complex models.
- Introduce geospatial data handling and weather-data fusion.

### 3.3 Success Criteria

The project is successful if it produces:

- a working collector that accumulates deduplicated PIREPs over time
- a documented parser and label mapping
- a reproducible training dataset
- a baseline classifier with per-class metrics
- an interactive or static geospatial visualization
- an analysis showing whether weather features add useful signal

## 4. Non-Goals

The initial project will not:

- produce an operational flight safety tool
- provide real-time safety-critical turbulence forecasts
- replace official aviation weather products
- require manual labeling of reports
- guarantee global coverage
- optimize for production-scale cloud deployment before the research pipeline is
  validated

## 5. Users And Stakeholders

### 5.1 Primary Users

- The project mentor or senior developer guiding the work.
- The junior developer implementing the pipeline.
- Reviewers evaluating the project as a portfolio or research artifact.

### 5.2 Possible Future Users

- Aviation students or researchers.
- Data science reviewers.
- Aerospace recruiters or technical interviewers.
- Weather or flight-safety analysts, if the project matures.

## 6. Data Sources

### 6.1 Aircraft Reports

Primary source:

```text
https://aviationweather.gov/data/cache/aircraftreports.cache.csv.gz
```

The collector currently uses the Aviation Weather Center aircraft reports cache.

**Measured live 2026-08-20 (supersedes earlier estimates):**

| Property | Value |
| --- | --- |
| Cache window | rolling **~90 minutes** (`observation_time` 00:08-01:37Z) |
| Snapshot size | ~1,530 rows, 44 columns, ~85 KB gzipped |
| Accrual | ~32,000 reports/day |
| Report mix | **91.8% AIREP**, 8.2% PIREP/Urgent PIREP |
| Turbulence label yield | 6.6% of all rows; **67% of pilot reports** |
| Labeled PIREPs | ~1,500-2,400/day |
| Storage | ~2.2 KB/row (~2 GB/month raw, ~210 MB/month gzipped) |

There is no backfill endpoint. Downtime is permanent data loss, which is why the
collector must run on an always-on host (`deploy/RUNBOOK.md`).

### 6.2 Weather Observations

Candidate sources for later phases:

- METAR observations from Aviation Weather Center endpoints
- AIRMET and SIGMET products
- gridded wind and temperature aloft data
- other NOAA/NWS public aviation weather products

Weather fusion should begin with the simplest reliable source and only expand
after the matching logic is validated.

## 7. Key Concepts

### 7.1 PIREP

A pilot report describing actual in-flight weather or flight conditions.

### 7.2 AIREP

An aircraft report that may be automated or less useful for text-based modeling.
The project must decide whether AIREPs should be excluded from the classifier.

### 7.3 Turbulence Label

The target class derived from structured turbulence fields. The proposed classes
are:

- `None`
- `Light`
- `Moderate`
- `Severe`

### 7.4 Label Leakage

Label leakage occurs if the model input contains the structured turbulence field,
such as `/TB MOD`. The classifier would then learn to read the answer instead of
learning from descriptive language. All training text must remove turbulence
label fields.

## 8. System Scope

The system is divided into five phases.

### 8.1 Phase 0: Data Discovery

Purpose: understand the aircraft report schema and inspect real examples.

Current implementation:

- `explore.py`

Expected outputs:

- printed schema report
- resolved column names
- PIREP/AIREP distribution
- turbulence label distribution
- sample reports
- `snapshot.csv`

### 8.2 Phase 1: Data Collection

Purpose: collect and store reports over time.

Current implementation:

- `collector.py`
- `pireps.db`

Expected outputs:

- deduplicated SQLite database
- typed extracted fields
- full raw JSON for every row
- collection run history

### 8.3 Phase 2: Parsing And Labeling

Purpose: convert collected reports into a clean supervised learning dataset.

Expected outputs:

- parser for relevant PIREP fields
- turbulence label mapper
- leakage-safe text cleaner
- clean training dataframe

### 8.4 Phase 3: Classification

Purpose: train and evaluate models that predict turbulence severity.

Expected outputs:

- TF-IDF baseline model
- evaluation report with per-class metrics
- optional transformer model
- model comparison notes

### 8.5 Phase 4: Geospatial Visualization

Purpose: visualize reports and predictions on a map.

Expected outputs:

- map colored by severity
- filters for time, altitude, and aircraft type
- ability to inspect individual reports
- optional comparison of actual vs predicted severity

### 8.6 Phase 5: Weather Fusion

Purpose: enrich reports with nearby weather observations and investigate
relationships between weather signatures and turbulence.

Expected outputs:

- spatial-temporal weather matching logic
- weather-enriched report dataset
- analysis of weather features vs turbulence severity
- optional classifier using both text and weather features

## 9. Functional Requirements

### 9.1 Data Discovery Requirements

FR-001: The system shall fetch the current aircraft reports cache.

FR-002: The system shall print all available columns and non-null counts.

FR-003: The system shall resolve likely columns for raw text, turbulence,
report type, aircraft type, latitude, longitude, altitude, and observation time.

FR-004: The system shall save a local snapshot for offline parser development.

FR-005: The system shall print sample reports for manual inspection.

### 9.2 Collection Requirements

FR-006: The system shall poll the aircraft reports cache.

FR-007: The system shall use a custom `User-Agent`.

FR-008: The system shall store reports in SQLite.

FR-009: The system shall deduplicate repeated reports.

FR-010: The deduplication key shall include observation time, location, and raw
text.

FR-011: The system shall preserve the full raw source row for every report.

FR-012: The system shall store collection run metadata.

FR-013: The system shall provide a statistics command showing collection
progress.

FR-014: The system shall handle no-content responses without treating them as
failures.

FR-015: The system shall back off when rate limited.

### 9.3 Parsing And Labeling Requirements

FR-016: The system shall map raw turbulence values into the agreed severity
classes.

FR-017: The system shall handle combined values such as `LGT-MOD` by selecting
the maximum severity.

FR-018: The system shall handle negative turbulence reports.

FR-019: The system shall remove turbulence fields from model input text.

FR-020: The system shall produce a dataset containing cleaned text, label,
location, altitude, aircraft type, and observation time where available.

FR-021: The system shall document unmapped or ambiguous turbulence values.

### 9.4 Classification Requirements

FR-022: The system shall train a baseline classifier before any transformer
model.

FR-023: The baseline shall use text features from cleaned PIREP text.

FR-024: The system shall use a stratified train/test split where class counts
allow it.

FR-025: The system shall report precision, recall, and F1 for each class.

FR-026: The system shall address class imbalance using class weights or another
documented training-only method.

FR-027: The system may train a transformer model after the baseline is complete.

FR-028: The system shall compare upgraded models against the baseline.

### 9.5 Mapping Requirements

FR-029: The system shall plot reports using latitude and longitude.

FR-030: The system shall color reports by turbulence severity.

FR-031: The system should support filtering by time.

FR-032: The system should support filtering or grouping by altitude band.

FR-033: The system should expose report details on click or hover.

FR-034: The system should identify suspicious geospatial results for manual
review.

### 9.6 Weather Fusion Requirements

FR-035: The system shall match each eligible PIREP to nearby weather observation
data using location and time.

FR-036: The system shall record matching distance and time difference.

FR-037: The system shall extract weather features from matched observations.

FR-038: The system shall validate a sample of weather matches manually.

FR-039: The system shall analyze relationships between weather features and
turbulence severity.

FR-040: The system may test whether weather features improve model performance.

## 10. Non-Functional Requirements

### 10.1 Reproducibility

NFR-001: The project shall document commands needed to reproduce each phase.

NFR-002: Generated datasets shall be reproducible from raw stored data when
possible.

NFR-003: Label mapping rules shall be versioned or documented clearly.

### 10.2 Data Integrity

NFR-004: Raw collected rows shall be preserved.

NFR-005: Duplicate reports shall not be inserted into the main reports table.

NFR-006: The project shall include a backup process for the SQLite database.

### 10.3 Maintainability

NFR-007: Parsing, labeling, training, mapping, and fusion logic should be split
into clear modules as the project grows.

NFR-008: Tests should cover critical data transformations.

NFR-009: Ambiguous assumptions should be documented near the code or in project
docs.

### 10.4 Ethics And Safety

NFR-010: The project shall clearly state that outputs are experimental and not
for operational flight decisions.

NFR-011: The project shall avoid representing model predictions as official
aviation guidance.

### 10.5 Performance

NFR-012: The collector shall respect public data-source rate limits.

NFR-013: Baseline model training should run on a normal laptop.

NFR-014: The map should remain usable on the expected collected dataset size.

## 11. Proposed Data Model

### 11.1 Raw Reports Table

The current `reports` table stores:

- hash
- fetched_at
- obs_time
- report_type
- raw_text
- turbulence
- aircraft
- lat
- lon
- altitude
- raw_json

### 11.2 Future Training Dataset

The training dataset should include:

- report_hash
- raw_text_original
- raw_text_clean
- turbulence_raw
- severity_label
- report_type
- aircraft_type
- latitude
- longitude
- flight_level
- obs_time
- split or fold assignment, if fixed splits are used

### 11.3 Future Weather-Enriched Dataset

The weather-enriched dataset should include:

- report_hash
- matched_station
- station_latitude
- station_longitude
- report_to_station_distance
- report_to_weather_time_delta
- wind_speed
- wind_direction
- temperature
- pressure
- visibility or ceiling indicators, if useful
- derived weather features

## 12. Evaluation Requirements

The classifier evaluation shall include:

- class distribution before splitting
- train/test split description
- confusion matrix
- per-class precision
- per-class recall
- per-class F1
- macro F1
- weighted F1
- notes on class imbalance

The map evaluation shall include:

- manual inspection of sample plotted reports
- checks for impossible coordinates
- checks for altitude parsing errors

The weather fusion evaluation shall include:

- manual validation of sampled matches
- distribution of match distances
- distribution of match time differences
- documented limitations of the chosen weather source

## 13. Risks

### 13.1 Data Volume Risk

Severe turbulence reports may be rare. The project may need several weeks of
collection to gather enough examples.

### 13.2 Label Quality Risk

PIREPs may contain messy turbulence descriptions. Label mapping must be inspected
against real values instead of guessed.

### 13.3 Label Leakage Risk

If `/TB` remains in model input, the model evaluation will be invalid.

### 13.4 Geospatial Parsing Risk

Location fields may be inconsistent. Incorrect geocoding can produce misleading
maps and bad weather matches.

### 13.5 Weather Matching Risk

Surface METAR observations may not represent conditions at flight level. Weather
fusion conclusions must state this limitation clearly.

### 13.6 Scope Risk

The project can grow quickly. The baseline classifier and map should be completed
before adding complex weather fusion or transformer modeling.

## 14. Open Decisions

- ~~What exact turbulence values appear?~~ **Answered:** `LGT`, `NEG`, `MOD`,
  `LGT-MOD` observed. **No `SEV` in 2,600 reports** — plan for three classes.
  Turbulence appears in up to two layer groups (`turbulence_intensity` and
  `turbulence_intensity.1`); the mapper must take the max across both.
- ~~Should AIREPs be excluded from the text classifier?~~ **Answered:** yes for
  text (they carry no prose), but *keep them* — they supply `temp_c`,
  `wind_dir_degrees`, and `wind_speed_kt` **at flight level** on ~91% of rows,
  which is a better weather-fusion source than surface METAR.
- **NEW, unresolved:** after stripping `/TB` to prevent leakage, **62% of labeled
  PIREPs have zero residual text** (median residual: 0 chars; only 2% exceed 20
  chars). The text-classification premise in Section 2 may not be supportable.
  Section 8.4 likely needs reframing toward structured/atmospheric features.
- What minimum text length makes a report usable for NLP?
- Should altitude be used as a model feature or only for filtering and analysis?
- Should the final map be a static artifact, notebook output, or web app?
- Which weather source should be used first for fusion?
- What is the minimum acceptable dataset size before training the first model?
- Should model splits be random, time-based, or grouped by location/time to
  reduce leakage?

## 15. Initial Milestones

### Milestone 1: Collector Running

- Run `explore.py`.
- Pin resolved columns in `collector.py`.
- Run `collector.py --once`.
- Start continuous collection.
- Confirm `python collector.py --stats` works.

### Milestone 2: Clean Dataset

- Inspect turbulence values.
- Finalize label mapping.
- Implement leakage-safe text cleaning.
- Export first training dataframe.

### Milestone 3: Baseline Model

- Train TF-IDF baseline.
- Produce evaluation report.
- Identify class imbalance problems.

### Milestone 4: Map

- Plot labeled reports.
- Add severity colors.
- Add basic filters or facets.
- Use map to inspect geospatial quality.

### Milestone 5: Weather Fusion Prototype

- Match reports to nearest weather observations.
- Validate sample matches manually.
- Produce first weather-feature analysis.

## 16. Revision Log

| Date | Version | Notes |
| --- | --- | --- |
| 2026-08-16 | 0.1 | Initial requirements draft. |
| 2026-08-20 | 0.2 | Live schema verified; cache window corrected 15 days -> ~90 min; label yield, report mix, and severity distribution measured; leakage-residual finding recorded. |


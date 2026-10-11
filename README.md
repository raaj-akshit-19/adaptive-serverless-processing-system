# Adaptive Serverless Processing System

A serverless system that assesses physiological risk and adapts how a workload
is processed, using the risk level and the performance of earlier runs.

> **Reconstruction status.** This repository is a reconstruction of an earlier
> academic project. The architecture and behaviour come from the original
> project and its invention disclosure. The original source code was not
> available, so the code-level rules (event format, risk numbers, adaptive
> rules, Worker computation, alert message) were written new for this
> repository. They are labelled **NEW** throughout and are not claimed to be
> the original implementation. See
> [Reconstruction status by item](#reconstruction-status-by-item).
>
> **AWS deployment is intentionally not performed in this
> repository-generation phase.** Nothing here has been deployed to or tested
> against AWS.

## Stack

- Python
- AWS Lambda
- Amazon DynamoDB
- Amazon SNS
- Amazon CloudWatch (Lambda's standard logs)

## Problem

Physiological readings differ in urgency. Processing every workload the same
way wastes resources on routine data and delays the response to urgent data.
This system scores the risk of the incoming readings, chooses the processing
strategy accordingly, raises an alert for critical readings without waiting
for processing, and records how each run performed so later decisions can use
it.

## Architecture

```text
Physiological Input (SpO2, heart rate, HRV, respiratory rate)
    │
    ▼
Controller Function
    │
    ├── Risk Assessment ─────────────→ risk score, risk level
    │
    ├── Feedback Storage (read) ←───── DynamoDB item "config"
    │
    ├── Adaptive Decision ───────────→ execution mode, segment size
    │
    ├── Execution
    │     ├── Sequential → Worker Function
    │     └── Parallel   → Segmentation → Worker Functions
    │
    ├── Result Consolidation
    │
    ├── Performance Measurement
    │
    └── Feedback Update ─────────────→ DynamoDB item "config"


Critical risk
    │   asynchronous Lambda invocation
    ▼
Alert Microservice
    │   SNS publish
    ▼
SNS topic


CloudWatch Logs ← standard output of every Lambda
```

Critical risk activates an independent Alert Microservice pathway that does
not depend on completion of the primary processing workflow.

## Reconstruction status by item

### Confirmed

Established by the original project and its invention disclosure:

- The architecture: a **Controller Function**, **Worker Functions**, a
  **Feedback Storage** layer and a dedicated **Alert Microservice**.
- **Risk-based adaptive execution**: risk is evaluated from SpO2, heart rate,
  HRV and respiratory rate, each contributing to a composite score through a
  weighted deviation from its normal range, with threshold evaluation. The
  risk level controls execution.
- **Sequential processing** for normal conditions and **distributed
  (parallel) processing** for elevated conditions, with **dynamic
  segmentation** of higher-intensity inputs.
- **Result consolidation**: Worker outputs are merged into the final result.
- **Feedback**: execution duration is recorded and used to refine
  segmentation and later decisions.
- **Critical alert behaviour**: the alert pathway is activated when risk
  exceeds a threshold, independently of and before completion of primary
  processing.
- AWS Lambda, DynamoDB, SNS and CloudWatch as the project's services.
- The configuration record shown under
  [Feedback storage](#feedback-storage), and the Worker file beginning with
  `import time` and `def lambda_handler(event, context):`.

### Derived

Implementation choices that make the confirmed behaviour executable. They are
**not** recovered historical details, and each is confined to one module.

| Choice | Where |
|---|---|
| Asynchronous Lambda invocation from the Controller to the Alert Microservice | `src/controller/alert_activation.py` |
| Alert Microservice publishes to SNS itself | `src/alert/sns_alert.py` |
| Synchronous Lambda invocation from the Controller to the Worker | `src/controller/dispatch.py` |
| Python threads for parallel dispatch, one Worker invocation per segment | `src/controller/dispatch.py` |
| One Worker deployment, invoked concurrently; sequential mode is one invocation with the whole workload | `src/controller/dispatch.py`, `src/worker` |
| Segmentation mechanism: consecutive slices | `src/controller/segmentation.py` |
| Module structure and function interfaces; order of the Controller's steps | `src/` |
| Environment variable names, handler paths, deployment packaging | see [Deployment](#deployment-not-performed) |

### New (reconstructed)

Written for this repository because the original logic could not be
recovered. None of it is claimed to be the original implementation.

| Item | Where |
|---|---|
| Event schema and validation rules | `src/controller/lambda_function.py` |
| Normal ranges, critical limits and weights | `src/controller/risk_assessment.py` |
| Risk score calculation and risk level cut-offs | `src/controller/risk_assessment.py` |
| Execution-mode rule and segment-size heuristic | `src/controller/adaptive_decision.py` |
| Meanings given to `chunk_size`, `last_time` and `last_size` | `src/controller/adaptive_decision.py` |
| Normalized feedback metric, the ±10% feedback rule and the chunk size bounds | `src/controller/adaptive_decision.py` |
| Worker aggregation statistics and Worker event and result shapes | `src/worker/lambda_function.py` |
| Consolidation rule and final result shape | `src/controller/consolidation.py` |
| Alert request fields, alert subject and message | `src/controller/alert_activation.py`, `src/alert/sns_alert.py` |
| Controller response structure | `src/controller/lambda_function.py` |

**The reconstructed risk thresholds and weights are implementation
assumptions and are not clinical thresholds.**

**The original disclosure mentions predictive execution-time estimation, but
the original prediction mechanism was not recovered. The reconstructed
implementation uses historical execution performance as feedback rather than
claiming to reproduce the original prediction model.**

## Input event (NEW)

One event carries a list of readings. Each reading is one snapshot of the
four parameters. The workload is the list; the workload size is its length.

```json
{
  "readings": [
    {"spo2": 97, "heart_rate": 72, "hrv": 45, "respiratory_rate": 16},
    {"spo2": 93, "heart_rate": 105, "hrv": 30, "respiratory_rate": 22}
  ]
}
```

| Field | Type | Rule |
|---|---|---|
| `readings` | list | required, at least one reading |
| `spo2` | number, percent | above 0 and at most 100 |
| `heart_rate` | number, beats per minute | above 0 |
| `hrv` | number, milliseconds | 0 or above |
| `respiratory_rate` | number, breaths per minute | above 0 |

All four fields are required in every reading. An invalid event fails with a
`ValueError` naming the reading and field; no Worker runs, no alert is sent
and the configuration is not updated.

## Risk model (NEW)

Each parameter has a normal range and a critical limit on each side. Its
deviation is 0 inside the normal range and rises linearly to 1 at the
critical limit, where it is capped.

| Parameter | Normal range | Critical low | Critical high | Weight |
|---|---|---|---|---|
| SpO2 | 95–100 | 85 | none | 0.35 |
| Heart rate | 60–100 | 40 | 140 | 0.25 |
| Respiratory rate | 12–20 | 6 | 30 | 0.25 |
| HRV | 20–100 | 5 | 200 | 0.15 |

```text
deviation = 0                                                inside the normal range
          = (normal_low − value) / (normal_low − critical_low)    below it
          = (value − normal_high) / (critical_high − normal_high) above it

risk_score = 0.35·spo2 + 0.25·heart_rate + 0.25·respiratory_rate + 0.15·hrv   (deviations)
```

| Level | Rule |
|---|---|
| Normal | score below 0.10 |
| Moderate | score from 0.10 up to, but not including, 0.50 |
| Critical | score 0.50 or above, or any single parameter at its critical limit |

For an event, every reading is scored, and three separate results are kept:

- the event's risk level is the highest severity among the readings;
- the event's risk score is the highest numerical score among the readings;
- the reading responsible for the highest severity is retained, and is the
  reading sent with a Critical alert.

The score and the retained reading can come from different readings: a
reading that is Critical through the critical-limit rule may score lower than
a Moderate reading in the same event. A Critical reading anywhere in the
event triggers the alert.

## Adaptive execution (NEW rules)

**Execution mode**

| Risk level | Mode |
|---|---|
| Normal | sequential |
| Moderate or Critical | parallel if the workload size is larger than the segment size, otherwise sequential |

**Segment size**

```text
Moderate:  segment_size = chunk_size
Critical:  segment_size = max(1, chunk_size // 2)
then:      segment_size = max(segment_size, ceil(workload_size / 10))   at most 10 segments
```

`chunk_size` comes from the stored configuration, so earlier runs influence
how the current workload is divided.

## Feedback storage

The DynamoDB table holds one item. This is the known record from the original
project, and it is the item to seed the table with:

```json
{
  "id": "config",
  "chunk_size": 2,
  "last_time": 0.1,
  "last_size": 4
}
```

The original meanings of the three fields are unknown. This implementation
interprets them as follows; these meanings are **NEW**:

| Attribute | DynamoDB type | NEW meaning |
|---|---|---|
| `id` | String, partition key | always `"config"` |
| `chunk_size` | Number | readings per segment |
| `last_time` | Number | total execution time of the previous run, in seconds |
| `last_size` | Number | workload size of the previous run, in readings |

**Reading the record**

| Stored value | Behaviour |
|---|---|
| whole item missing | the run fails with a "seed the table" error; no item is created |
| `chunk_size` missing | 2 is used |
| `chunk_size` below 1 or above 10 | 1 or 10 is used |
| `last_time` or `last_size` missing or not above 0 | previous timing is invalid; no comparison is made |

**Feedback update (NEW heuristic)**

The update always follows this order:

1. Read the existing configuration.
2. Keep the previous `chunk_size` (bounded), `last_time` and `last_size`.
3. Execute the current workload using the previous `chunk_size`.
4. Measure the current execution time.
5. Compare the normalized execution-time feedback metrics, using the previous
   values:
   `current = execution_time / workload_size`,
   `previous = last_time / last_size`.
6. Decide the new chunk size, then bound it to 1–10:
   - current more than 10% above previous → `chunk_size − 1`
   - current more than 10% below previous → `chunk_size + 1`
   - otherwise unchanged
7. Store the new `chunk_size`, `last_time` (3 decimals) and `last_size` in one
   write.

The comparison is made only after a parallel run with valid previous timing.
Sequential runs record `last_time` and `last_size` but never change
`chunk_size`. The previous values are never overwritten before the decision
is calculated.

The reconstructed feedback policy decreases or increases the segment size
based on whether normalized execution time has worsened or improved relative
to the previous run. It is a heuristic and is not claimed to be optimal.

## Worker and result (NEW)

The Worker receives `{"readings": [...]}` for one segment and returns the
count and, for each parameter, the sum, minimum and maximum:

```json
{
  "count": 2,
  "spo2":             {"sum": 190, "min": 93, "max": 97},
  "heart_rate":       {"sum": 177, "min": 72, "max": 105},
  "hrv":              {"sum": 75,  "min": 30, "max": 45},
  "respiratory_rate": {"sum": 38,  "min": 16, "max": 22}
}
```

Consolidation adds the counts and sums, keeps the smallest minimum and the
largest maximum, and reports the mean (sum ÷ count, 2 decimals). Processing
the whole workload at once and processing it in segments give the same final
result.

**Controller response**

```json
{
  "risk_level": "Critical",
  "risk_score": 0.601,
  "mode": "parallel",
  "execution_time": 0.9,
  "alert_activated": true,
  "result": {
    "count": 6,
    "spo2":             {"mean": 93.33, "min": 88, "max": 97},
    "heart_rate":       {"mean": 99.67, "min": 72, "max": 125},
    "hrv":              {"mean": 31.17, "min": 15, "max": 45},
    "respiratory_rate": {"mean": 20.83, "min": 16, "max": 26}
  }
}
```

This is the response for [examples/sample_event.json](examples/sample_event.json)
with the seed configuration. `execution_time` is whatever is measured; 0.9 is
illustrative.

## Alert (NEW request and message)

When the event's risk level is Critical, the Controller invokes the Alert
Microservice asynchronously with:

```json
{
  "risk_level": "Critical",
  "risk_score": 0.601,
  "reading": {"spo2": 88, "heart_rate": 125, "hrv": 15, "respiratory_rate": 26}
}
```

`risk_score` is the event's risk score and `reading` is the reading
responsible for the Critical level.

The Alert Microservice publishes to SNS with the subject
`Critical physiological risk alert` and this message:

```text
Critical physiological risk detected.
Risk score: 0.601
SpO2: 88 %
Heart rate: 125 bpm
HRV: 15 ms
Respiratory rate: 26 breaths/min
```

The alert does not depend on workload size or on processing. If the
activation call fails, the failure is logged, processing continues and the
response reports `"alert_activated": false`.

## Failure behaviour and known limitations

| Situation | Behaviour |
|---|---|
| Invalid input | fails with a clear error; no processing, no alert, no feedback update |
| Configuration item missing | fails with a "seed the table" error |
| DynamoDB unavailable | the run fails; a Critical alert has already been activated |
| Worker failure | the run fails; the configuration is not updated; a Critical alert has already been activated |
| Alert activation failure | logged; processing continues |

- **Concurrent Controller invocations** are not coordinated. Each reads the
  record and the last write wins.
- **The feedback comparison ignores mode.** The previous run may have been
  sequential, and the record has no field to say so.
- There are no retries.

## Historical experimental results

Reported in the invention disclosure:

| InputCondition | Mode | SegmentSize | ExecutionTime |
|---|---|---:|---:|
| Normal | Sequential | 10 | 0.10 s |
| Moderate | Parallel | 20 | 1.70 s |
| Critical | Parallel + Alert | 24 | 1.20 s |

These rows are kept only as historical observations. The original meaning of
`SegmentSize` is unknown, and its values cannot be mapped to the `segment_size`
used in this repository, which is a new implementation concept. No formula
was derived from these rows, and this implementation does not reproduce them
and is not claimed to.

## Project structure

```text
├── README.md
├── requirements.txt          runtime dependency (boto3)
├── requirements-dev.txt      adds pytest
├── pytest.ini
├── src/
│   ├── controller/           Controller Function
│   │   ├── lambda_function.py    handler, input validation, pipeline
│   │   ├── risk_assessment.py    risk score and level
│   │   ├── adaptive_decision.py  execution mode, segment size, feedback update
│   │   ├── dynamodb_config.py    read and write the configuration item
│   │   ├── segmentation.py       split the workload into segments
│   │   ├── dispatch.py           invoke the Worker, sequentially or in parallel
│   │   ├── consolidation.py      merge Worker results
│   │   └── alert_activation.py   invoke the Alert Microservice
│   ├── worker/               Worker Function
│   │   └── lambda_function.py    handler: summary statistics for one segment
│   └── alert/                Alert Microservice
│       ├── lambda_function.py    handler: build the message, publish
│       └── sns_alert.py          message text and SNS publish
├── examples/
│   └── sample_event.json     six readings, one of them Critical
└── tests/
```

## Local testing

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements-dev.txt
pytest
```

All tests are local unit tests. `boto3` is replaced with in-memory
stand-ins, and `tests/conftest.py` fails any test that tries to create a real
AWS client. The Controller tests run the real Worker handler behind the
stand-in Lambda client, so they exercise the whole pipeline. There are no
tests that require AWS, and none have been run against AWS.

| Test file | Covers |
|---|---|
| `test_input_validation.py` | event schema and validation errors |
| `test_risk_assessment.py` | deviation, score, levels, critical limits, highest-risk reading |
| `test_adaptive_decision.py` | execution mode, segment size, chunk size bounds, feedback update |
| `test_worker_and_consolidation.py` | Worker statistics, merging, whole versus segmented |
| `test_controller.py` | the handler end to end, alert activation and failure cases |
| `test_alert.py`, `test_alert_activation.py` | alert request, message, SNS publish, asynchronous invocation |
| `test_config.py` | configuration item read and write |
| `test_segmentation.py`, `test_dispatch.py` | slicing and Worker invocation |

## Deployment (not performed)

The repository contains all application code. Deploying it requires only the
AWS setup below, none of which has been carried out.

### AWS resources that must exist

- One DynamoDB table with partition key `id` (String), seeded with the
  configuration item shown under [Feedback storage](#feedback-storage).
- One SNS topic for critical alerts.
- Three Lambda functions on a Python runtime.

### Lambda functions and handler names

Each package is zipped so that its folder is at the zip root.

| Function | Package contents | Handler |
|---|---|---|
| Controller | `src/controller` | `controller.lambda_function.lambda_handler` |
| Worker | `src/worker` | `worker.lambda_function.lambda_handler` |
| Alert Microservice | `src/alert` | `alert.lambda_function.lambda_handler` |

### Controller timeout

AWS Lambda functions use a default timeout of 3 seconds unless one is
configured. The Controller waits for its synchronous Worker invocations
during processing, so an actual deployment should configure a Controller
timeout that suits the expected workload and Lambda execution time. This is a
deployment configuration consideration, not part of the reconstructed
algorithm.

### Environment variables

The variable names are derived choices, not historical names. No credentials
are stored in the code; `boto3` uses each function's execution role.

| Function | Variable | Value |
|---|---|---|
| Controller | `CONFIG_TABLE_NAME` | name of the DynamoDB table |
| Controller | `WORKER_FUNCTION_NAME` | name or ARN of the Worker function |
| Controller | `ALERT_FUNCTION_NAME` | name or ARN of the Alert Microservice function |
| Alert Microservice | `ALERT_TOPIC_ARN` | ARN of the SNS topic |

### IAM permissions

All three roles need the standard Lambda logging permissions.

| Function | Additional permissions |
|---|---|
| Controller | `dynamodb:GetItem` and `dynamodb:PutItem` on the table; `lambda:InvokeFunction` on the Worker and Alert Microservice functions |
| Worker | none |
| Alert Microservice | `sns:Publish` on the topic |

### Python dependencies

`boto3` only. It is already included in the AWS Lambda Python runtime, so the
deployment packages need no bundled libraries.

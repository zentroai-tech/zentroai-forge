# API Reference

Base URL: `http://localhost:8000`

## Auth

- Header: `X-API-Key`
- If `AGENT_COMPILER_API_KEY` is unset, auth is effectively disabled
- If `AGENT_COMPILER_REQUIRE_AUTH_FOR_READS=true`, read endpoints also require the key

## System

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | API metadata |
| GET | `/health` | Health check |
| GET | `/engines` | Available engine adapters |
| POST | `/admin/cleanup` | Cleanup old exports |
| GET | `/admin/migrations` | Migration status |
| GET | `/admin/config` | Sanitized runtime config |

## Flows

| Method | Path | Purpose |
|---|---|---|
| POST | `/flows` | Create flow from IR v2 payload |
| GET | `/flows` | List flows |
| GET | `/flows/{flow_id}` | Get flow detail |
| PUT | `/flows/{flow_id}` | Update flow |
| DELETE | `/flows/{flow_id}` | Delete flow |
| GET | `/flows/{flow_id}/versions` | List versions |
| GET | `/flows/{flow_id}/env` | List env vars |
| POST | `/flows/{flow_id}/env` | Upsert env var |
| DELETE | `/flows/{flow_id}/env/{var_id}` | Delete env var |
| POST | `/flows/{flow_id}/runs` | Execute run |
| POST | `/flows/{flow_id}/runs/stream` | Stream run events |
| GET | `/flows/{flow_id}/runs` | List runs |
| DELETE | `/flows/{flow_id}/runs` | Delete all runs for a flow |
| POST | `/flows/{flow_id}/chat` | Chat wrapper |
| POST | `/flows/{flow_id}/batch` | Batch execution |
| GET | `/flows/{flow_id}/costs` | Token/cost summary |
| POST | `/flows/{flow_id}/export` | Create export |
| GET | `/flows/{flow_id}/exports` | List exports |

## Runs

| Method | Path | Purpose |
|---|---|---|
| GET | `/runs/{run_id}` | Run detail with timeline |
| DELETE | `/runs/{run_id}` | Delete run |
| POST | `/runs/{run_id}/replay` | Replay run |
| GET | `/runs/{run_id}/artifacts` | Step artifacts |
| GET | `/runs/{run_id}/events` | Agent event timeline |
| POST | `/runs/diff` | Diff two runs |
| GET | `/runs/{run_id}/compare/{other_run_id}` | Compare two runs |

## Exports

| Method | Path | Purpose |
|---|---|---|
| GET | `/exports/{export_id}` | Export metadata |
| GET | `/exports/{export_id}/manifest` | Manifest preview |
| GET | `/exports/{export_id}/file` | Fetch one exported file |
| GET | `/exports/{export_id}/download` | Download ZIP |
| POST | `/exports/{export_id}/gitops` | Open PR from export |

## Evals

| Method | Path | Purpose |
|---|---|---|
| POST | `/evals/flows/{flow_id}/suites` | Create suite |
| GET | `/evals/flows/{flow_id}/suites` | List suites |
| GET | `/evals/suites/{suite_id}` | Get suite |
| PATCH | `/evals/suites/{suite_id}/config` | Update thresholds/config |
| DELETE | `/evals/suites/{suite_id}` | Delete suite |
| POST | `/evals/suites/{suite_id}/cases` | Create case |
| GET | `/evals/suites/{suite_id}/cases` | List cases |
| PUT | `/evals/cases/{case_id}` | Update case |
| DELETE | `/evals/cases/{case_id}` | Delete case |
| POST | `/evals/suites/{suite_id}/run` | Execute suite |
| GET | `/evals/suites/{suite_id}/runs` | List suite runs |
| GET | `/evals/runs/{eval_run_id}` | Get eval run |
| GET | `/evals/runs/{eval_run_id}/results` | Get case results |
| GET | `/evals/runs/{eval_run_id}/report` | Download report |
| POST | `/evals/suites/{suite_id}/dataset` | Upload JSONL dataset |

## Tools

| Method | Path | Purpose |
|---|---|---|
| GET | `/tool-contracts` | List tool contracts |
| GET | `/tool-contracts/{tool_name}` | Get one contract |
| POST | `/tool-contracts/validate` | Validate IR tool references |

## Debug

| Method | Path | Purpose |
|---|---|---|
| POST | `/debug/flows/{flow_id}/start` | Start debug session |
| POST | `/debug/sessions/{session_id}/command` | Send command |
| GET | `/debug/sessions/{session_id}` | Get debug session |
| DELETE | `/debug/sessions/{session_id}` | Delete debug session |
| POST | `/debug/flows/{flow_id}/nodes/{node_id}/test` | Test one node |

## Templates and projects

| Method | Path | Purpose |
|---|---|---|
| GET | `/project-templates` | List templates |
| GET | `/project-templates/{template_id}` | Template detail |
| POST | `/project-templates/{template_id}/preview` | Preview generated IR |
| POST | `/projects` | Create project from template |
| POST | `/projects/{project_id}/regenerate-from-template` | Placeholder, currently `501` |

## Credentials, providers, logs, and GitOps

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/credentials` | List credentials |
| POST | `/api/credentials` | Create credential |
| PATCH | `/api/credentials/{credential_id}` | Update credential |
| DELETE | `/api/credentials/{credential_id}` | Delete credential |
| POST | `/api/credentials/{credential_id}/test` | Test credential |
| GET | `/api/providers` | List providers |
| GET | `/api/providers/{provider}/models` | List models |
| POST | `/api/providers/{provider}/models/refresh` | Refresh models |
| GET | `/logs/stream` | Log SSE stream |
| GET | `/logs/recent` | Recent logs |
| GET | `/gitops/status` | GitOps status |
| POST | `/gitops/connect` | Connect GitHub session |
| DELETE | `/gitops/disconnect` | Disconnect GitHub session |
| GET | `/gitops/repos` | List repos |
| GET | `/gitops/repos/{owner}/{repo}/branches` | List branches |
| GET | `/gitops/jobs/{job_id}` | Job status |

# Security Policy

## Scope

This repository is intended for local development and self-hosted deployments.
Review credential handling, runtime policies, and MCP settings before using it
in production.

## Reporting

Do not open a public issue for a suspected vulnerability.

Report security issues privately to the maintainers and include:

- affected component or file
- reproduction steps
- expected impact
- suggested mitigation, if known

## Secret handling

- Do not commit credentials, tokens, or populated `.env` files
- Use `.env.example`, `backend/.env.example`, and `frontend/.env.example`
  as templates only
- Set `FORGE_MASTER_KEY` if you want credential encryption enabled
- Restrict MCP command and tool allowlists outside local development

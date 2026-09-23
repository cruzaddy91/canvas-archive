# Security Policy

## Supported versions

This is a personal archival tool. Only the `main` branch is maintained.

## Reporting a vulnerability

If you find a security issue, please open a private report via GitHub Security Advisories
on this repository, or contact the maintainer directly. Do not open a public issue for
anything that could expose credentials or private course material.

## What this tool actually touches

Unlike a typical portfolio project that runs locally against nothing, canvas-archive
authenticates to two real external services and provisions real infrastructure:

- **Canvas API**, using a personal access token (`CANVAS_TOKEN` in `.env`), scoped to
  the student's own account. This token can read every course, assignment, and
  submission that account can see. Treat it as equivalent to your Canvas password:
  it is revocable from Canvas account settings if ever exposed.
- **GitHub**, via `gh auth token` (`core.git_ops._terraform_env`) rather than a raw
  personal access token stored in a file. Terraform uses this to provision one
  **private** repository per archived course. That delegation to the `gh` CLI's own
  credential store, instead of a `GITHUB_TOKEN` sitting in `.env`, is deliberate: one
  fewer place a long-lived credential can leak from.
- **Terraform state** (`infra/terraform.tfstate*`, gitignored) tracks the real,
  already-provisioned course repos. It is not a disposable artifact; losing or
  corrupting it orphans Terraform's record of infrastructure that still exists on
  GitHub.

The archived course repos themselves are the closest thing this project has to a
production surface. They hold real assignment content, in some cases including
other students' names surfaced through group assignments or class rosters. They must
stay **private**, which is enforced in `infra/main.tf`, not just a default someone
remembered to set once.

## Secrets handling

- No secrets are committed to this repository. Real values live only in a local,
  gitignored `.env` file (see [`.env.example`](.env.example) for the variable names).
- The Canvas token must never appear in source, tests, commit history, or log output.
  If one is ever committed, assume it is compromised and revoke it in Canvas
  immediately (Account > Settings > New Access Token replaces the old one).
- GitHub secret scanning and push protection are enabled on this repository.

# charlie

Map Cortex XSOAR content pack dependencies from the CLI.

[Charlie](/images/charlie.webp)

## Prereqs

- Install uv from [https://docs.astral.sh/uv/getting-started/installation/](https://docs.astral.sh/uv/getting-started/installation/)
- Access to a Cortex XSOAR content repository (git URL)

## Install

```bash
uv tool install git+https://github.com/bowenaguero/charlie
```

## Setup

Clones your content repo, indexes all playbook references into a local SQLite database, and saves the config.

```bash
charlie setup
```

## Usage

```bash
# Find all playbooks that call an automation
charlie scan --target MyAutomation --type automation

# Find all playbooks that call an integration command
charlie scan --target "Gmail|||send-mail" --type integration-command

# Find all playbooks that reference a sub-playbook
charlie scan --target "Phishing Investigation" --type playbook

# Find all playbooks that read or write an incident field
charlie scan --target severity --type field

# Override the repo path (skips managed clone)
charlie scan --target MyAutomation --type automation --repo /path/to/repo

# Export as an HTML graph
charlie scan --target MyAutomation --type automation --output html

# Export as a DOT file
charlie scan --target MyAutomation --type automation --output dot
```

## Re-index

After pulling changes to your content repo manually, re-run the indexer without re-cloning.

```bash
charlie reindex
```

## Component Types

| Type | Value | Description |
|---|---|---|
| Playbook | `playbook` | XSOAR playbook (referenced as a sub-playbook) |
| Automation | `automation` | Script/automation not tied to an integration |
| Integration command | `integration-command` | Command exposed by an integration (`Brand\|\|\|cmd` or `cmd`) |
| Field | `field` | Incident or indicator field (reads and writes) |

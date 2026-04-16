# charlie

Map Cortex XSOAR content pack dependencies from the CLI.

![Charlie](/images/charlie.webp)

## Background

XSOAR playbooks reference automations, integration commands, sub-playbooks, fields, layouts, and more — often across dozens of content packs. Understanding what depends on what before making a change is painful without tooling.

Charlie indexes your content repository into a local SQLite database, then lets you query dependency relationships in seconds. Given any component, it tells you which of your components use it, and renders the result as a tree, an interactive HTML graph, or a DOT file for downstream tooling.

## Prereqs

- Install uv from [https://docs.astral.sh/uv/getting-started/installation/](https://docs.astral.sh/uv/getting-started/installation/)
- Access to a Cortex XSOAR content repository (git URL) or a live XSOAR instance

## Install

```bash
uv tool install git+https://github.com/bowenaguero/charlie
```

## Setup

Clones your content repo (or downloads from a live XSOAR instance), indexes all references into a local SQLite database, and saves the config.

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

# Find all playbooks that use an integration
charlie scan --target Gmail --type integration

# Find all playbooks that use a list
charlie scan --target AllowedDomains --type list

# Find all playbooks that reference a layout
charlie scan --target "Phishing Layout" --type layout

# Find all playbooks that use a classifier
charlie scan --target PhishingClassifier --type classifier

# Find all playbooks that reference an incident type
charlie scan --target Phishing --type incidenttype

# Override the repo path (skips managed clone)
charlie scan --target MyAutomation --type automation --repo /path/to/repo

# Export as an HTML graph (opens in browser automatically)
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
| Integration | `integration` | Integration/connector (brand-level reference) |
| Field | `field` | Incident or indicator field (reads and writes) |
| Layout | `layout` | Incident layout definition |
| List | `list` | XSOAR list |
| Classifier | `classifier` | Content classifier |
| Incident type | `incidenttype` | Incident type definition |

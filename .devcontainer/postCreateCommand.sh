#! /usr/bin/env bash

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install system dependencies
sudo apt-get install -y ripgrep

# Install Dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install --install-hooks

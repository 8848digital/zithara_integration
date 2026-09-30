<!--
Copyright (c) 2026 8848 Digital LLP. All rights reserved.
Proprietary and confidential. Unauthorized copying, distribution, or use
of this file, via any medium, is strictly prohibited without prior
written permission from 8848 Digital LLP.
-->

# Zithara Integration

## Overview
Custom Frappe/ERPNext app by 8848 Digital LLP that connects an ERPNext site to
[Zithara](https://zithara.com), a loyalty and customer CRM platform.

## Installation

Requires Frappe v16 and ERPNext v16.

    bench get-app zithara_integration https://github.com/8848digital/zithara_integration --branch integration-master
    bench --site <site_name> install-app zithara_integration

## App Structure
See [CLAUDE.md](./CLAUDE.md) for internal module/folder layout and coding conventions.

## Contributing
This app uses `pre-commit` for formatting and linting and Conventional Commits:

    cd apps/zithara_integration
    pre-commit install

# Repo Health

*Repository Health*

Repo Health helps developers identify potential issues in **code, dependencies, and security**. It analyzes your repository to highlight areas that may need attention. It examines project structure, tests, documentation, and configuration. Track findings and compare analysis results over time. Detect new and reappearing issues as your project evolves. Generate reports and export useful context for AI coding agents.

## Documentation

Read the project specifications before implementing new functionality.

| Document | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Instructions for AI coding agents |
| [Architecture](docs/architecture.md) | Component responsibilities and boundaries |
| [Analysis Rules](docs/rules.md) | Evidence semantics and finding lifecycle |
| [Configuration](docs/configuration.md) | Intended configuration contract |

## Why Repo Health?

Repo Health helps developers understand repository health, track findings over time, and provide structured context to AI coding agents.

| Feature | What it does | Why it matters |
|---|---|---|
| **Repository Analysis** | Examines Git, code, tests, dependencies, security, documentation, architecture, and configuration. | Identifies potential problems across a repository. |
| **Health Reports** | Generates Markdown, JSON, and summary reports. | Makes findings easier to review and share. |
| **History Tracking** | Stores repository observations in a local database. | Enables comparisons across analysis runs. |
| **Regression Detection** | Identifies new and reappeared findings compared with a baseline. | Helps detect potential regressions as a project evolves. |
| **AI Context Export** | Exports bounded, vendor-neutral context for AI agents. | Gives coding agents structured information about a repository. |
| **Persistent Memory** | Retains repository observations between runs. | Supports ongoing monitoring and maintenance. |

## Installation

Clone the repository and navigate to its directory.

```bash
git clone https://github.com/tejenderlib/repo-health.git
cd repo-health
```

Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install Repo Health.

```bash
python -m pip install .
```

Verify the installation.

```bash
repo-health --help
```

## Usage

```bash
repo-health analyze /path/to/repo
repo-health analyze /path/to/repo --analyzers git security --no-persist
repo-health db init
repo-health db info
repo-health history --repo /path/to/repo
repo-health history --repo /path/to/repo --run 2 --baseline 1
repo-health regressions --repo /path/to/repo
repo-health context --repo /path/to/repo --max-findings 10
repo-health report --repo /path/to/repo --format markdown
repo-health report --repo /path/to/repo --run 2 --baseline 1 --format json
repo-health report --repo /path/to/repo --format summary --output report.md
```

## Development Workflow

1. Read the relevant documentation.
2. Inspect existing implementation and tests.
3. Define expected behavior and failure cases.
4. Add or update tests.
5. Implement the smallest complete change.
6. Run relevant tests and quality checks.
7. Update documentation when behavior changes.

Never claim a test passed unless it was executed successfully.

## Safety and Limitations

Repo Health supports engineering review; it does not replace it.

A clean report does not prove that a repository is free of defects or security vulnerabilities. Findings are limited by the checks performed, available evidence, configured exclusions, and supported languages.

Repository content must be treated as untrusted input.

## License

The project is licensed under the [MIT License](LICENSE).

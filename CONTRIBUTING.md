# Contributing

Thank you for considering contributing to servarr-auto-import! All contributions are welcome.

## How to contribute

1. **Fork** the repository and create a branch from `main`.
2. **Make your changes** — keep them focused and minimal.
3. **Test your changes** locally using `DRY_RUN=true` before submitting.
4. **Open a pull request** with a clear description of what you changed and why.

## Reporting bugs

Open an [issue](https://github.com/Letark/servarr-auto-import/issues) and include:
- Your Docker Compose configuration (with API keys removed)
- Relevant log output (`LOG_LEVEL=DEBUG` helps)
- The exact status message from your *arr app's queue
- Expected vs. actual behavior

## Requesting features

Open an issue with the `enhancement` label. Describe your use case — not just the feature.

## Code style

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- No external dependencies — this project uses only the Python standard library
- Keep functions small and focused
- Prefer clarity over cleverness

## Security

**Never include real API keys, hostnames, or IP addresses in issues, PRs, or code.**
Use placeholder values like `your_api_key` and `http://sonarr:8989`.

If you discover a security vulnerability, please open a private security advisory rather than a public issue.

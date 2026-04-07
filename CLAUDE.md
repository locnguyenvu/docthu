# docthu — agent instructions

## Documentation

When adding or changing any public-facing functionality (new function, new parameter, changed behaviour, new exception, new template syntax), update **`docs/api.md`** and **`llms.txt`** in the same commit/PR.

- `docs/api.md` — human-readable API reference for developers
- `llms.txt` — machine-readable summary for LLM coding assistants

Do not duplicate API details in `README.md`; it links to `docs/api.md` for the full reference.

# Contributing to ShiftLens

1. Set up with `python -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt`.
2. Before opening a pull request, run `.venv\Scripts\python -m pytest`. All tests must pass, and they never call a real model.
3. Keep these rules:
   - **Python owns the numbers.** Metrics stay deterministic. Explanations may only rephrase snapshot values and must pass `validate_explanation`.
   - **The deterministic fallback stays the default** and must work with no network or keys.
   - **Synthetic data only.** No real clubs, players, competitions, logos or licensed match data.
   - **Never commit secrets.** Keep keys in a local `.env`, which is git-ignored.
4. A change to the dataset shape bumps `schema_version` and updates the schema, the validator and `docs/data_contract.md` together.
5. Propose out-of-scope ideas in an issue. Check the [roadmap](README.md#roadmap) and
   [Future real-data integrations](docs/wiki/Future-Real-Data-Integrations.md) first.

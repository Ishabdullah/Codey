# Codey v1.0.1 Implementation Todo

## Packaging & Trust

- [ ] 1. Create `requirements.txt` (Scan imports and pin versions)
- [ ] 2. Create `tests/` suite:
    - [ ] `test_agent_parsing.py`
    - [ ] `test_patch.py`
    - [ ] `test_memory.py`
    - [ ] `test_codeyignore.py`
- [ ] 3. Token estimation improvement (core/tokens.py or similar)
    - [ ] Code heuristic (len/3) vs Prose (len/4)
- [ ] 4. Expand secret redaction patterns (core/sessions.py)
    - [ ] JWTs, AWS keys, Bearer tokens, SSH private keys

## Release

- [ ] 5. Bump version to 1.0.1 (utils/config.py)
- [ ] 6. Update Version History in README.md
- [ ] 7. Push to GitHub

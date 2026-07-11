<!-- Thanks for contributing! See CONTRIBUTING.md. -->

**What & why**
<!-- What does this change and why? Link any issue. -->

**Checklist**
- [ ] `pytest` passes locally
- [ ] Added/updated tests (bug fixes include a regression test)
- [ ] If a read path changed: a test proves an unauthorized requester can't see the memory
- [ ] Schema change (if any) is a forward-only migration that upgrades from the last release
- [ ] Web console parity + all-locale strings updated (if user-facing)
- [ ] CHANGELOG `[Unreleased]` updated (if behavior changed)
- [ ] Commits signed off (`git commit -s`, DCO)
- [ ] I am not aware of this breaking a surface in COMPATIBILITY.md (or I flagged it)

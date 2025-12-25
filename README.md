# Sigil

Sigil is an experimental, extensible scripting language and runtime focused on simplicity, plugin-driven extensibility, and a lightweight IDE for rapid iteration. Sigil aims to be a pragmatic tool for building small languages, automation pipelines, and developer tooling while keeping a clear steward-driven roadmap.

> **Status:** Active development — use at your own risk. The project is licensed under the **Vexon Open-Control License (VOCL) 1.0**. See `LICENSE` for full text.

---

## Quick links

- Repository: (this repo)  
- License: `LICENSE` (VOCL 1.0)  
- Contributing guidelines: `CONTRIBUTING.md`  
- Security contact: `SECURITY.md`  
- Code of Conduct: `CODE_OF_CONDUCT.md`

---

## Goals

- Provide a minimal, opinionated runtime for experimentation.  
- Make it easy to extend the language via plugins.  
- Ship a tiny cross-platform IDE for authoring and running Sigil scripts.  
- Keep a single project steward to preserve long-term design consistency.

---

## Features

- Small language core and VM  
- Plugin system for extending runtime and tools  
- Basic CLI + minimal IDE for editing and running scripts  
- Example plugins and documentation to get started

---

## Getting started

1. Clone the repository:

```bash
git clone https://github.com/TheServer-lab/sigil.git
cd sigil
```

2. Read the docs in `/docs` and `examples/` for sample scripts and plugin examples.

3. Run the IDE (when available) or use the runtime for scripts:

```bash
# Example — adjust to your local layout
python3 -m sigil.runtime examples/hello.sig
```

---

## Project layout 

```
sigil/
├─ core/                # runtime, parser, VM
├─ plugins/             # built-in plugins and examples
├─ ide/                 # minimal IDE sources
├─ installer/           # installer scripts, NSIS files
├─ docs/                # user and developer docs
├─ examples/            # sample .sig scripts
├─ LICENSE
├─ README.md
├─ CONTRIBUTING.md
└─ SECURITY.md
```

---

## License

This repository is released under the **Vexon Open-Control License (VOCL) 1.0**. VOCL is a source-available license that allows use, modification, redistribution, and commercial distribution while preserving creator control over future re-licensing decisions. VOCL is **not** an OSI-approved open-source license. See `LICENSE` for the full text.

---

## Contact

For private or sensitive contact (security reports, licensing questions, private partnerships) please email: **serverlabdev@proton.me**

---

## Releases and versioning

This project uses semantic versioning where possible. Milestone releases and changelogs are kept in `CHANGELOG.md`.

---

## Contributing

Contributions are welcome. Please read `CONTRIBUTING.md` before submitting issues or pull requests.

---

## A note on stewardship

Sigil is steward-driven. The project owner maintains final say on direction, API design, and releases. This helps keep the language cohesive as it evolves.

---

## Acknowledgements

Thanks to everyone who tests, files issues, or contributes small improvements. Your feedback is what will make this project more useful over time.

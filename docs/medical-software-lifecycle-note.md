# Medical-software lifecycle note

This repository demonstrates selected lifecycle practices; it is not developed under a certified
quality system and makes no conformity claim.

The currently published IEC 62304 consolidated edition defines a common framework for medical
device software lifecycle processes. ISO 14971:2019 defines a medical-device risk-management
process and was confirmed current by ISO in 2025. FDA's current software guidance emphasizes
documentation supporting safety and effectiveness claims. These sources motivate the structure
below, but their complete requirements are not reproduced here.

## Practice mapping

| Lifecycle concern | Repository evidence | Important gap |
|---|---|---|
| Development planning | README roadmap, requirements, architecture, verification plan | No approved quality plan, roles, independence, or formal review records |
| Requirements analysis | `software-requirements.md` with stable IDs | No clinical intended purpose, regulatory classification, or system-level allocation |
| Architectural/detailed design | `algorithm-design.md`, source modules, explicit equations | No hardware architecture, scanner interface, cybersecurity, or SOUP assessment |
| Unit implementation and verification | Unit tests, lint, Python-version CI | No validated toolchain or formal code-review signatures |
| Integration and system testing | Real carotid, physical phantom, backend comparison | Single public acquisition family; no production hardware integration |
| Risk management | `risk-management.md` linked to controls/evidence | No manufacturer risk policy, acceptability criteria, benefit-risk analysis, or post-production loop |
| Configuration management | Git history, data hashes, JSON evidence | No formal baseline approval, release authority, anomaly database, or retention policy |
| Problem resolution | Test failures and commits are inspectable | No controlled CAPA/problem-resolution process |
| Maintenance | Reproducible commands and CI | No released device, field monitoring, or maintenance plan |

## References

- [IEC 62304:2006+A1:2015 consolidated edition](https://webstore.iec.ch/en/publication/22794)
- [ISO 14971:2019](https://www.iso.org/standard/72704.html)
- [FDA Medical Device Software Guidance Navigator](https://www.fda.gov/medical-devices/regulatory-accelerator/medical-device-software-guidance-navigator)

Before any clinical or device use, a qualified manufacturer would need to establish the intended
purpose, jurisdiction, device classification, quality system, complete risk process, usability,
security, electrical/acoustic safety, clinical evaluation, validated production environment, and
regulatory strategy.

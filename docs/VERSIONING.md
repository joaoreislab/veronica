# Versioning policy

Veronica follows [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR** for incompatible changes to the documented public interface.
- **MINOR** for compatible new capabilities. The patch component resets to zero.
- **PATCH** for compatible bug fixes without new capabilities.

The public interface consists of documented helper commands and JSON operations, their documented required inputs and meanings, the structured state/export schema, and versioned artifact and recovery formats. Consumers should tolerate additional optional JSON fields. Generated Markdown and HTML views are derived presentations; their layout is not a stable parsing interface. Cooperative tokens are transient values, not a stable identifier or security API.

Released tags and their package contents remain unchanged. Presentation edits alone do not require a new skill version. Interface or runtime changes are classified before release. Previews use an explicit pre-release suffix where appropriate.

## Why 1.2.0 follows 1.1.2

The package initially released as 1.1.2 included compatible new functionality: deep diagnostics, recovery bundles, capture-receipt reconciliation and task-index pagination. A patch number understated that scope. Version 1.2.0 gives that feature package the appropriate minor-version classification, updates version labels and refines its public presentation. It retains the runtime behavior of 1.1.2.

The existing `v1.1.2` tag remains as a historical publication. Existing project state is not reset or reinitialized. This correction introduces no new runtime functionality or breaking interface change beyond that already published feature package.

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `SubjectAnalysis` refreshes that only remove analyses (nothing added) now
  strip the removed labels out of the existing metafile directly with
  `summarymodify --remove_label` and regenerate the pages from it, instead
  of falling back to a full rebuild of every remaining analysis. (#3)
- `PESummary.rename_analysis()`: explicitly rename a stored analysis in an
  already-published combined metafile via `summarymodify`, without
  triggering a re-run. Not wired into the automatic refresh cycle, since a
  before/after diff of resolved dependency names can't distinguish a
  rename from an unrelated removal and addition. (#3)
- Initial release of asimov-pesummary plugin
- PESummary pipeline integration for Asimov 0.7+
- Post-processing and visualization capabilities
- Multi-analysis result combination
- HTCondor job submission
- Result collection and asset management
- Comprehensive test suite
- `[asimov]` optional dependency group for explicit asimov integration

### Changed
- Extracted PESummary integration from Asimov core into standalone plugin
- Removed deprecation warning from Asimov 0.6
- Updated version constraint to require asimov>=0.7

### Fixed
- Updated dependency constraint to support asimov 0.7
- `PESummary` now overrides `detect_completion()` instead of falling back to
  the base `Pipeline`'s unconditional no-op. Without this, once a
  production's HTCondor job exited and asimov stopped tracking a job id for
  it, `asimov monitor`'s no-job-id branch could never detect that the run
  had actually finished -- it repeated "is stuck; attempting a rescue"
  forever, regardless of how long a genuine, correctly labelled
  `posterior_samples.h5` had already existed on disk.

## [0.1.0] - TBD

### Added
- First public release

[Unreleased]: https://git.ligo.org/asimov/asimov-pesummary/compare/v0.1.0...HEAD
[0.1.0]: https://git.ligo.org/asimov/asimov-pesummary/releases/tag/v0.1.0

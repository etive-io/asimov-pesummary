# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
- `_submit_single_analysis` now raises a clear `PipelineException` when a
  production's `waveform` meta is missing `approximant`, `minimum
  frequency`, or `reference frequency`, instead of letting an unguarded
  dict lookup raise a raw `KeyError` from deep inside `submit_dag`. This
  matches the validation `_submit_subject_analysis` already performed for
  each combined analysis.

## [0.1.0] - TBD

### Added
- First public release

[Unreleased]: https://git.ligo.org/asimov/asimov-pesummary/compare/v0.1.0...HEAD
[0.1.0]: https://git.ligo.org/asimov/asimov-pesummary/releases/tag/v0.1.0

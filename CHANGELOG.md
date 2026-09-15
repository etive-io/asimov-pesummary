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
  production's `waveform`/`quality` meta is missing `approximant`,
  `reference frequency`, or `minimum frequency`, instead of letting an
  unguarded dict lookup raise a raw `KeyError` from deep inside
  `submit_dag`. This matches the validation `_submit_subject_analysis`
  already performed for each combined analysis.
- `--f_low` is now read from `production.meta["quality"]["minimum
  frequency"]` instead of `production.meta["waveform"]["minimum
  frequency"]`, in both `_submit_single_analysis` and
  `_submit_subject_analysis`. `approximant`/`reference frequency` are
  waveform properties, but the minimum (starting) frequency is a
  `quality` setting in asimov's schema -- the same place every other
  asimov pipeline (bilby, lalinference, rift, bayeswave, and asimov
  core's own previous built-in `pesummary` pipeline) reads it from.
  `waveform.minimum frequency` was never populated by any of those, so
  this key was effectively always missing unless a ledger happened to
  duplicate it there by hand.

## [0.1.0] - TBD

### Added
- First public release

[Unreleased]: https://git.ligo.org/asimov/asimov-pesummary/compare/v0.1.0...HEAD
[0.1.0]: https://git.ligo.org/asimov/asimov-pesummary/releases/tag/v0.1.0

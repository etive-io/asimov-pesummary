Unreleased
==========

Bug Fixes
---------

**Config file, PSDs and calibration envelopes come from the analysis being summarised**
  A single-analysis job passed ``summarypages`` its own generated config file, not the one
  of the analysis in ``needs``, and its PSDs and calibration envelopes were only those
  advertised by that analysis directly. Pipelines such as bilby advertise just their
  samples and config, so no ``--psds`` or ``--calibration`` was passed at all. The config
  is now the upstream analysis's (as for each source analysis of a subject analysis), and
  PSDs and calibration envelopes are looked up through the upstream analysis's own
  ``needs`` (for example ``generate-psd``) when it doesn't provide them, for single and
  subject analyses alike.

**Job files written to the production's run directory**
  The job script and HTCondor ``output``/``error``/``log`` files were written to the
  event's working directory, so two PESummary productions of one event (for example a
  per-analysis page and a combined page) overwrote each other's ``pesummary.sh`` and logs.
  They now go in the production's own run directory, which is created if needed. A
  production with no run directory still uses the event's working directory.

**Single-analysis jobs inherit waveform configuration from ``needs``**
  A single-analysis ``PESummary`` production previously required ``waveform``
  (approximant / reference frequency) and ``likelihood`` (minimum frequency) to be set on
  the PESummary production itself, and failed with a ``PipelineException`` otherwise, even
  though the upstream analysis it summarises already defines them. Missing entries are now
  filled in from the analyses listed in ``needs``; values set on the PESummary production
  still take precedence.

0.2.0
=====

This is a feature and bug-fix release.

New Features
------------

**Efficient SubjectAnalysis Refresh**
  ``summarypages`` can only append new analyses to an already-published combined page; it
  has no way to retract or rename a label in place. A ``SubjectAnalysis`` refresh that
  only *removes* an analysis (nothing added) now strips the removed label out of the
  existing metafile directly with ``summarymodify --remove_label`` and regenerates the
  pages from it, instead of falling back to a full rebuild of every remaining analysis. A
  refresh that both adds and removes analyses at once still falls back to a full rebuild,
  as before.

**``rename_analysis()``**
  Adds ``PESummary.rename_analysis()``, wrapping ``summarymodify``'s label-rename support
  to rename a stored analysis in an already-published metafile without triggering a
  re-run. It is deliberately not wired into the automatic refresh cycle, since a
  before/after diff of resolved dependency names alone can't distinguish a rename from an
  unrelated removal and addition.

Bug Fixes
---------

**Stuck-Monitor Detection**
  ``PESummary`` now overrides ``detect_completion()`` instead of falling back to the base
  ``Pipeline``'s unconditional no-op. Previously, once a production's HTCondor job exited
  and asimov stopped tracking a job id for it, ``asimov monitor``'s no-job-id branch could
  never detect that the run had actually finished, and repeated "is stuck; attempting a
  rescue" forever, regardless of how long a genuine, correctly labelled
  ``posterior_samples.h5`` had already existed on disk.

**Missing Waveform/Likelihood Meta**
  ``_submit_single_analysis`` now raises a clear ``PipelineException`` when a production's
  ``waveform``/``likelihood`` meta is missing ``approximant``, ``reference frequency``, or
  ``minimum frequency``, instead of letting an unguarded dict lookup raise a raw
  ``KeyError`` from deep inside ``submit_dag``, matching the validation
  ``_submit_subject_analysis`` already performed for each combined analysis.

**Minimum Frequency Location**
  ``--f_low`` is now read from ``production.meta["likelihood"]["minimum frequency"]``
  instead of ``production.meta["waveform"]["minimum frequency"]``, in both
  ``_submit_single_analysis`` and ``_submit_subject_analysis``. ``approximant`` and
  ``reference frequency`` are genuinely ``waveform`` properties, but the minimum
  (starting) frequency is a ``likelihood`` setting in asimov 0.7's schema --
  ``waveform.minimum frequency`` was never populated by asimov at all, so this key was
  effectively always missing unless a ledger happened to duplicate it there by hand.

Breaking Changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

GitHub Pull Requests
--------------------

+ `github#6 <https://github.com/etive-io/asimov-pesummary/pull/6>`_: Fix: PESummary never
  overrode detect_completion(), so monitor could never mark it finished
+ `github#7 <https://github.com/etive-io/asimov-pesummary/pull/7>`_: Fix waveform/likelihood
  meta lookups for missing-frequency KeyErrors
+ `github#8 <https://github.com/etive-io/asimov-pesummary/pull/8>`_: Remove/rename analyses
  during SubjectAnalysis refresh without a full rebuild

0.1.2
=====

This is a bug-fix release, which does not introduce any new backwards-incompatible
features.

Bug Fixes
---------

**Non-Scalar Sample Paths**
  ``collect_assets()["samples"]`` is not always a single path string -- ``bilby_pipe``'s
  collector returns a list even when there's exactly one match. Both the single-analysis
  and ``SubjectAnalysis`` submission paths now normalise either shape via a new
  ``PESummary._single_sample_path()`` helper, instead of appending a list into the
  ``summarypages`` command and crashing with a ``TypeError`` at submission time. A
  production with no samples at all now raises a clear ``PipelineException`` instead of
  silently appending an empty dict.

Breaking Changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

GitHub Pull Requests
--------------------

+ `github#5 <https://github.com/etive-io/asimov-pesummary/pull/5>`_: Handle
  collect_assets()["samples"] being a list, not just a scalar path

0.1.1
=====

This is a feature and bug-fix release.

New Features
------------

**SubjectAnalysis Support**
  Adds a ``SubjectAnalysis`` version of the pipeline, permitting the automatic creation of
  combined and comparison summary pages across multiple asimov subjects/analyses.

**End-to-End Testing**
  Adds an end-to-end testing workflow using a mock gravitational-wave inference pipeline
  to exercise a full PESummary analysis without needing a real upstream sampler run.

Bug Fixes
---------

**Config Template Crash**
  ``PESummary`` now provides its own ``config_template``. Previously, asimov's generic
  ``manage build`` step fell back to looking for a ``pesummary.ini`` template inside
  asimov core's own package -- a leftover path from before PESummary was split into a
  separate plugin -- and raised ``jinja2.exceptions.TemplateNotFound`` for any real
  production without a pre-seeded ini file.

Breaking Changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

GitHub Pull Requests
--------------------

+ `github#1 <https://github.com/etive-io/asimov-pesummary/pull/1>`_: Add an end-to-end
  testing workflow
+ `github#2 <https://github.com/etive-io/asimov-pesummary/pull/2>`_: Add subject analysis
+ `github#4 <https://github.com/etive-io/asimov-pesummary/pull/4>`_: Give PESummary a
  config_template, fixing a TemplateNotFound crash in manage build

0.1.0
=====

Initial public release of ``asimov-pesummary``, extracting PESummary post-processing
support out of core asimov into its own plugin package, following the pattern later
established for GraceDB and the other bundled pipelines.

New Features
------------

**Standalone PESummary Plugin**
  ``asimov-pesummary`` registers itself via asimov's ``asimov.pipelines`` entry-point
  mechanism, so installing the package is sufficient for asimov to discover and use it --
  no in-tree pipeline code required. It builds a ``summarypages`` command from the
  per-production waveform, data-quality, calibration, and PSD meta-data, submits it as an
  HTCondor job, and returns the path to the resulting PESummary HDF5 metafile as a
  downstream asset.

**Multi-Analysis Combination**
  Supports combining results from multiple upstream analyses into a single comparison
  page.

**Optional ``asimov`` Extra**
  Adds an ``[asimov]`` optional dependency group for projects that want to depend on this
  plugin together with an explicit ``asimov`` version constraint.

Breaking Changes
----------------

**Requires asimov 0.7+**
  This plugin only supports asimov 0.7 and later, matching the version from which
  PESummary support was removed from asimov core in favour of this plugin. The
  deprecation warning asimov 0.6 attached to its own bundled ``pesummary`` pipeline no
  longer applies, since the implementation now lives here.

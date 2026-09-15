"""Defines the interface with generic analysis pipelines."""

import importlib.resources
import os

from asimov import utils  # NoQA
from asimov import config, logger, logging, LOGGER_LEVEL  # NoQA
from asimov.scheduler_utils import create_job_from_dict  # NoQA

import otter  # NoQA
from asimov.storage import Store  # NoQA
from asimov.pipeline import Pipeline, PipelineException, PipelineLogger  # NoQA


class PESummary(Pipeline):
    """
    A postprocessing pipeline add-in using PESummary.

    A production using this pipeline may be either a regular analysis
    (post-processing a single upstream production's samples) or an asimov
    ``SubjectAnalysis`` (combining several productions' samples into one set
    of summary pages). ``SubjectAnalysis`` productions marked ``refreshable:
    true`` are automatically resubmitted by asimov's monitor loop whenever
    their resolved source analyses change; when that happens here, one of
    three things is submitted depending on how the resolved set changed
    since the last run:

    - analyses added only: the newly-added analyses are passed to
      ``summarypages``, using its own ``--add_to_existing``/
      ``--existing_webdir`` flags to append them to the already-published
      pages rather than recombining everything from scratch;
    - analyses removed only (nothing added): ``summarypages`` has no way to
      retract a label from an existing page in place, so instead
      ``summarymodify --remove_label`` strips the removed analyses out of
      the existing metafile directly, and ``summarypages`` is re-run
      against that trimmed metafile to regenerate the pages -- cheap, since
      none of the surviving analyses' posteriors need recomputing;
    - anything else (a mix of additions and removals, the first run, or a
      previous page that's gone missing on disk): a full rebuild is
      triggered, recombining every currently-resolved analysis from
      scratch.

    ``rename_analysis()`` exposes a related ``summarymodify`` operation
    (renaming a stored label) directly, for callers to invoke explicitly --
    it isn't wired into the automatic refresh above, since a before/after
    diff of resolved dependency names alone can't distinguish "renamed"
    from "removed one, added an unrelated one".
    """

    executable = os.path.join(
        config.get("pipelines", "environment"), "bin", "summarypages"
    )
    modify_executable = os.path.join(
        config.get("pipelines", "environment"), "bin", "summarymodify"
    )
    name = "PESummary"

    def __init__(self, production, category=None):
        # Imported here rather than at module level: asimov's own
        # asimov/analysis.py imports asimov/pipelines/__init__.py (to build
        # known_pipelines) before it finishes defining SubjectAnalysis, and
        # pipelines/__init__.py loads every registered third-party pipeline
        # plugin -- including this one -- as part of that same import. A
        # module-level `from asimov.analysis import SubjectAnalysis` here
        # would hit asimov.analysis mid-initialisation and raise ImportError,
        # which asimov's plugin loader swallows silently, dropping this
        # pipeline (and this package's other entry points) from
        # known_pipelines with no visible error.
        from asimov.analysis import SubjectAnalysis

        self.production = production
        self.subject = production.event
        self.is_subject_analysis = isinstance(production, SubjectAnalysis)

        self.category = category if category else production.category
        self.logger = logger
        self.meta = self.production.meta["postprocessing"][self.name.lower()]

        # Required by the base Pipeline.scheduler property; not calling
        # super().__init__() here since this class sets up its attributes
        # differently (e.g. category fallback, plain module logger).
        self._scheduler = None

    @property
    def config_template(self):
        """
        A minimal bundled config template.

        Asimov's generic ``manage build`` step calls ``production.make_config()``
        to render a production's own ``.ini`` from a template, whenever one
        doesn't already exist in the event repository (see
        ``repository.find_prods()``). Without this, asimov falls back to
        looking for a ``pesummary.ini`` template inside its own package,
        which doesn't exist there any more -- PESummary moved out of asimov
        core into this plugin -- so ``make_config()`` raises
        ``TemplateNotFound`` (see ``FakeCBCPipeline.config_template`` in
        ``testing.py``, which hit and documented this same gap first).
        The rendered file is what ``summarypages --config`` receives
        (see ``_submit_single_analysis``/``_submit_subject_analysis``);
        PESummary's own actual behaviour is controlled by the explicit CLI
        flags built from ``self.meta`` elsewhere in this class, so this only
        needs to be a valid, renderable ini for provenance/display purposes.
        """
        return str(
            importlib.resources.files("asimov_pesummary").joinpath(
                "configs/pesummary.ini"
            )
        )

    def _webdir(self):
        return os.path.join(
            config.get("project", "root"),
            config.get("general", "webroot"),
            self.subject.name,
            self.production.name,
            "pesummary",
        )

    def results(self):
        """
        Fetch the results file from this post-processing step.

        A dictionary of results will be returned with the description
        of each results file as the key.  These may be nested if it
        makes sense for the output, for example skymaps.

        For example::

            {'metafile': '/home/asimov/working/samples/metafile.hd5',
             'skymaps': {'H1': '/another/file/path', ...}
            }

        Returns
        -------
        dict
           A dictionary of the results.
        """
        self.outputs = self._webdir()
        metafile = os.path.join(self.outputs, "samples", "posterior_samples.h5")

        return dict(metafile=metafile)

    def collect_assets(self):
        """
        Advertise this pipeline's combined metafile, in case a further
        downstream step ever needs to consume it.
        """
        return {"samples": self.results()["metafile"]}

    def detect_completion(self):
        """
        Detect that this production's own ``summarypages`` run has finished.

        The base ``Pipeline.detect_completion()`` is an unconditional no-op
        (always falsy). Once this production's HTCondor job has exited and
        asimov's monitor loop is no longer tracking a job id for it,
        ``asimov monitor``'s no-job-id branch
        (``_handle_no_condor_job`` in asimov's ``monitor_states.py``) relies
        entirely on this method to decide whether to mark the production
        ``finished``; without an override here it always finds this falsy
        and repeatedly logs "is stuck; attempting a rescue" -- forever,
        since the base ``resurrect()`` is an equally unconditional no-op
        that never raises, so the production never progresses no matter how
        long or how often it's polled, even once a genuine, correctly
        labelled ``posterior_samples.h5`` already exists on disk.

        Delegates to ``detect_completion_processing()``, which already
        implements the right check for this pipeline's own output: that
        ``posterior_samples.h5`` exists, is readable, and (for a
        ``SubjectAnalysis``) contains every expected analysis's label as a
        top-level group.
        """
        return self.detect_completion_processing()

    def build_dag(self, user=None, dryrun=False):
        """
        No-op: PESummary has no separate build step. All of the work
        happens in ``submit_dag``, but asimov's generic ``manage build
        submit`` CLI unconditionally calls ``build_dag`` on every pipeline
        before ``submit_dag``, so this must exist.
        """
        pass

    def _append_shared_options(self, command):
        """
        Append the ``postprocessing.pesummary`` meta-driven flags shared by
        both single-analysis and subject-analysis submissions.
        """
        if "cosmology" in self.meta:
            command += ["--cosmology", self.meta["cosmology"]]
        if "redshift" in self.meta:
            command += ["--redshift_method", self.meta["redshift"]]
        if "skymap samples" in self.meta:
            command += ["--nsamples_for_skymap", str(self.meta["skymap samples"])]

        if "evolve spins" in self.meta:
            if "forwards" in self.meta["evolve spins"]:
                command += ["--evolve_spins_fowards", "True"]
            if "backwards" in self.meta["evolve spins"]:
                command += ["--evolve_spins_backwards", "precession_averaged"]

        if "multiprocess" in self.meta:
            command += ["--multi_process", str(self.meta["multiprocess"])]

        if self.meta.get("regenerate"):
            posteriors = self.meta.get("regenerate posteriors")
            if not posteriors:
                raise PipelineException(
                    "postprocessing.pesummary.regenerate is set, but "
                    "'regenerate posteriors' is missing or empty."
                )
            command += ["--regenerate", " ".join(posteriors)]

        if "calculate" in self.meta:
            if "precessing snr" in self.meta["calculate"]:
                command += ["--calculate_precessing_snr"]

    def _submit_description(self):
        """
        Build the HTCondor submit description fields shared by every
        PESummary job, regardless of whether it runs a single
        ``summarypages`` command or a chained ``summarymodify`` +
        ``summarypages`` script. Caller fills in ``executable`` and
        ``arguments``.
        """
        submit_description = {
            "output": f"{self.subject.work_dir}/pesummary.out",
            "error": f"{self.subject.work_dir}/pesummary.err",
            "log": f"{self.subject.work_dir}/pesummary.log",
            "request_cpus": self.meta["multiprocess"],
            "getenv": "true",
            "batch_name": f"Summary Pages/{self.subject.name}/{self.production.name}",
            "request_memory": "8192MB",
            "should_transfer_files": "YES",
            "request_disk": "8192MB",
        }
        if "accounting group" in self.meta:
            submit_description["accounting_group_user"] = config.get("condor", "user")
            submit_description["accounting_group"] = self.meta["accounting group"]
        return submit_description

    def _submit(self, command, dryrun):
        """
        Write the job script, build the submit description, and submit (or,
        if ``dryrun``, just print what would happen). Used for a plain,
        single ``summarypages`` invocation -- both the single-analysis path
        and the subject-analysis add/full-rebuild paths.
        """
        with utils.set_directory(self.subject.work_dir):
            with open("pesummary.sh", "w") as bash_file:
                bash_file.write(f"{self.executable} " + " ".join(command))

        self.logger.info(
            f"PE summary command: {self.executable} {' '.join(command)}",
        )

        if dryrun:
            print("PESUMMARY COMMAND")
            print("-----------------")
            print(" ".join(command))
        self.subject = self.production.event
        submit_description = self._submit_description()
        submit_description["executable"] = self.executable
        submit_description["arguments"] = " ".join(command)

        if dryrun:
            print("SUBMIT DESCRIPTION")
            print("------------------")
            print(submit_description)

        if not dryrun:
            job = create_job_from_dict(submit_description)
            cluster_id = self.scheduler.submit(job)
        else:
            cluster_id = 0

        return cluster_id

    def _submit_chain(self, steps, dryrun):
        """
        Write a small ``bash -e`` script running an ordered sequence of
        PESummary executables, then submit it as a single HTCondor job
        (stopping at the first failing step).

        Used where one ``summarypages`` invocation isn't enough: removing
        or renaming an analysis in an already-published combined page
        means editing the existing metafile with ``summarymodify`` first,
        then re-rendering the pages from it with ``summarypages``.

        Parameters
        ----------
        steps : list of (str, list of str)
            ``(executable, arguments)`` pairs, run in order.
        """
        lines = ["#!/bin/bash", "set -e"]
        lines += [f"{executable} " + " ".join(args) for executable, args in steps]
        script = "\n".join(lines) + "\n"
        script_path = os.path.join(self.subject.work_dir, "pesummary.sh")

        with utils.set_directory(self.subject.work_dir):
            with open("pesummary.sh", "w") as bash_file:
                bash_file.write(script)

        self.logger.info(f"PE summary command:\n{script}")

        if dryrun:
            print("PESUMMARY COMMAND")
            print("-----------------")
            print(script)
        self.subject = self.production.event
        submit_description = self._submit_description()
        # Run via /bin/bash rather than relying on pesummary.sh's own
        # executable bit, since nothing here guarantees the filesystem
        # this is written to preserves permissions (e.g. some shared/NFS
        # mounts, or the mocked filesystem in tests).
        submit_description["executable"] = "/bin/bash"
        submit_description["arguments"] = script_path

        if dryrun:
            print("SUBMIT DESCRIPTION")
            print("------------------")
            print(submit_description)

        if not dryrun:
            job = create_job_from_dict(submit_description)
            cluster_id = self.scheduler.submit(job)
        else:
            cluster_id = 0

        return cluster_id

    def submit_dag(self, dryrun=False):
        """
        Run PESummary on the results of this job.
        """
        if self.is_subject_analysis:
            return self._submit_subject_analysis(dryrun=dryrun)
        return self._submit_single_analysis(dryrun=dryrun)

    @staticmethod
    def _single_sample_path(samples):
        """
        Normalise a ``collect_assets()["samples"]`` value to a single path.

        Different upstream pipelines return this differently: some (e.g.
        bilby_pipe's ``Bilby.collect_assets``) return a list, built from a
        glob lookup over the run directory; others already return a single
        string. ``summarypages --samples`` takes one path per analysis
        being submitted here, so pick the first entry when given a
        list/tuple rather than passing the whole sequence through as a
        single command argument -- which fails downstream (`" ".join`
        raises ``TypeError``) once the command is assembled into a string.
        """
        if isinstance(samples, (list, tuple)):
            return samples[0] if samples else None
        return samples

    def _submit_single_analysis(self, dryrun=False):
        configfile = self.production.event.repository.find_prods(
            self.production.name, self.category
        )[0]
        label = str(self.production.name)

        command = ["--webdir", self._webdir(), "--labels", label]

        command += ["--gw"]
        command += [
            "--approximant",
            self.production.meta["waveform"]["approximant"],
        ]

        command += [
            "--f_low",
            str(min(self.production.meta["waveform"]["minimum frequency"].values())),
            "--f_ref",
            str(self.production.meta["waveform"]["reference frequency"]),
        ]

        self._append_shared_options(command)

        if "nrsur" in self.production.meta["waveform"]["approximant"].lower():
            command += ["--NRSur_fits"]

        # Config file
        command += [
            "--config",
            os.path.join(
                self.production.event.repository.directory, self.category, configfile
            ),
        ]
        # Samples
        sample_path = self._single_sample_path(
            self.production._previous_assets().get("samples")
        )
        if not sample_path:
            raise PipelineException(
                f"PESummary production {self.production.name} has no samples "
                "available from its upstream analysis."
            )
        command += ["--samples", sample_path]

        # PSDs
        psds = {
            ifo: os.path.abspath(psd)
            for ifo, psd in self.production._previous_assets().get("psds", {}).items()
        }
        if len(psds) > 0:
            command += ["--psds"]
            for key, value in psds.items():
                command += [f"{key}:{value}"]

        # Calibration envelopes
        cals = {
            ifo: os.path.abspath(psd)
            for ifo, psd in self.production._previous_assets()
            .get("calibration", {})
            .items()
        }
        if len(cals) > 0:
            command += ["--calibration"]
            for key, value in cals.items():
                command += [f"{key}:{value}"]

        return self._submit(command, dryrun)

    def _submit_subject_analysis(self, dryrun=False):
        """
        Run PESummary on the combined results of several source analyses.

        See the class docstring for how the first run, an add-only
        refresh, a remove-only refresh, and everything else are each
        handled differently.
        """
        source_analyses = list(self.production.analyses)
        if not source_analyses:
            raise PipelineException(
                f"PESummary subject analysis {self.production.name} has no "
                "resolved source analyses."
            )

        current_names = sorted(analysis.name for analysis in source_analyses)
        previous_names = self.production.resolved_dependencies
        webdir = self._webdir()
        page_exists = os.path.exists(os.path.join(webdir, "home.html"))

        previous_set = set(previous_names) if previous_names is not None else None
        current_set = set(current_names)

        incremental = bool(
            previous_set is not None
            and previous_set <= current_set
            and current_set - previous_set
            and page_exists
        )
        # Strictly fewer resolved analyses than last time, and nothing new
        # -- a pure removal, handled by editing the existing metafile
        # in place rather than recombining everything from scratch.
        removal_only = bool(
            previous_set is not None
            and current_set < previous_set
            and page_exists
        )

        if removal_only:
            return self._submit_subject_analysis_removal(
                removed=sorted(previous_set - current_set),
                webdir=webdir,
                dryrun=dryrun,
            )

        if incremental:
            analyses_to_submit = [
                analysis
                for analysis in source_analyses
                if analysis.name not in previous_names
            ]
        else:
            analyses_to_submit = source_analyses

        labels, approximants, f_lows, f_refs = [], [], [], []
        samples_list, config_list = [], []
        psds, cals = {}, {}

        for analysis in analyses_to_submit:
            assets = analysis.pipeline.collect_assets()
            samples = self._single_sample_path(assets.get("samples"))
            if not samples:
                self.logger.warning(
                    f"No samples available for {analysis.name}; skipping"
                )
                continue

            waveform = analysis.meta.get("waveform", {})
            if not {"approximant", "minimum frequency", "reference frequency"} <= (
                waveform.keys()
            ):
                raise PipelineException(
                    f"PESummary subject analysis {self.production.name}: "
                    f"{analysis.name} is missing waveform configuration "
                    "(approximant / minimum frequency / reference frequency) "
                    "required to combine it."
                )

            labels.append(analysis.name)
            samples_list.append(samples)
            approximants.append(waveform["approximant"])
            f_lows.append(str(min(waveform["minimum frequency"].values())))
            f_refs.append(str(waveform["reference frequency"]))

            configfile = analysis.event.repository.find_prods(
                analysis.name, analysis.category
            )[0]
            config_list.append(
                os.path.join(
                    analysis.event.repository.directory, analysis.category, configfile
                )
            )

            if not psds:
                psds = {
                    ifo: os.path.abspath(psd)
                    for ifo, psd in assets.get("psds", {}).items()
                }
            if not cals:
                cals = {
                    ifo: os.path.abspath(cal)
                    for ifo, cal in assets.get("calibration", {}).items()
                }

        if not labels:
            raise PipelineException(
                f"PESummary subject analysis {self.production.name} has no "
                "analyses with samples to add."
            )

        command = ["--webdir", webdir, "--labels"] + labels
        command += ["--gw"]
        command += ["--approximant"] + approximants
        command += ["--f_low"] + f_lows
        command += ["--f_ref"] + f_refs

        self._append_shared_options(command)

        if any("nrsur" in approximant.lower() for approximant in approximants):
            command += ["--NRSur_fits"]

        if incremental:
            command += ["--add_to_existing", "--existing_webdir", webdir]

        command += ["--config"] + config_list
        command += ["--samples"] + samples_list

        if psds:
            command += ["--psds"]
            for key, value in psds.items():
                command += [f"{key}:{value}"]

        if cals:
            command += ["--calibration"]
            for key, value in cals.items():
                command += [f"{key}:{value}"]

        # Set before submitting (matching the single-analysis convention of
        # treating "submitted" as "resolved"), so a later refresh's
        # staleness check compares against what this run is about to
        # process, and detect_completion_processing() knows which HDF5
        # groups to expect once it finishes. Use what was actually
        # submitted (previously-resolved names plus this round's labels),
        # not current_names -- an analysis skipped above (no samples yet)
        # must stay unresolved, or it would never be considered "new" on a
        # later refresh once its samples do appear, and
        # detect_completion_processing() would expect an HDF5 group for it
        # that will never exist.
        self.production.resolved_dependencies = sorted(
            set(previous_names or []) | set(labels)
        )

        return self._submit(command, dryrun)

    def _submit_subject_analysis_removal(self, removed, webdir, dryrun=False):
        """
        Drop one or more analyses from an already-published combined page,
        without recombining the analyses that remain.

        Called from ``_submit_subject_analysis`` when a refresh finds the
        resolved source analyses have only shrunk since the last
        successful run (nothing new, one or more gone). Runs
        ``summarymodify --remove_label`` against the existing metafile to
        strip the removed analyses' data out of it directly, then re-runs
        ``summarypages`` against that trimmed metafile so the published
        pages/plots no longer reference them. Neither step re-samples or
        recombines the analyses that remain -- a pesummary metafile
        carries its own stored labels, and ``summarypages`` uses those
        (ignoring/warning on any ``--labels`` passed alongside a metafile
        input), so the surviving analyses are picked up automatically once
        the removed ones are gone from the file.
        """
        metafile = self.results()["metafile"]
        if not os.path.exists(metafile):
            raise PipelineException(
                f"PESummary subject analysis {self.production.name}: cannot "
                f"remove {', '.join(removed)} -- no existing metafile found "
                f"at {metafile}."
            )

        modify_command = [
            "--samples", metafile,
            "--webdir", webdir,
            "--remove_label", *removed,
            "--overwrite",
        ]
        regenerate_command = ["--webdir", webdir, "--samples", metafile, "--gw"]
        if "multiprocess" in self.meta:
            regenerate_command += ["--multi_process", str(self.meta["multiprocess"])]

        cluster_id = self._submit_chain(
            [
                (self.modify_executable, modify_command),
                (self.executable, regenerate_command),
            ],
            dryrun,
        )

        self.production.resolved_dependencies = sorted(
            set(self.production.resolved_dependencies) - set(removed)
        )

        return cluster_id

    def rename_analysis(self, old_label, new_label, dryrun=False):
        """
        Rename a stored analysis in this subject analysis's published
        metafile, without re-running or recombining anything.

        This is not wired into the automatic refresh cycle: given only a
        before/after diff of resolved dependency names, asimov can't tell
        "an analysis was renamed" apart from "one was removed and an
        unrelated one was added". Call this directly -- e.g. from a
        one-off script -- when a production has been renamed in the
        ledger and its already-computed results should carry over under
        the new name rather than triggering a full re-run.

        Parameters
        ----------
        old_label : str
            The analysis's current stored label.
        new_label : str
            The label to rename it to.
        dryrun : bool, optional
            If True, print the commands that would be run rather than
            submitting them.
        """
        if not self.is_subject_analysis:
            raise PipelineException(
                "rename_analysis() only applies to PESummary SubjectAnalysis "
                "productions."
            )

        webdir = self._webdir()
        metafile = self.results()["metafile"]
        if not os.path.exists(metafile):
            raise PipelineException(
                f"PESummary subject analysis {self.production.name}: cannot "
                f"rename '{old_label}' -- no existing metafile found at "
                f"{metafile}."
            )

        modify_command = [
            "--samples", metafile,
            "--webdir", webdir,
            "--labels", f"{old_label}:{new_label}",
            "--overwrite",
        ]
        regenerate_command = ["--webdir", webdir, "--samples", metafile, "--gw"]
        if "multiprocess" in self.meta:
            regenerate_command += ["--multi_process", str(self.meta["multiprocess"])]

        cluster_id = self._submit_chain(
            [
                (self.modify_executable, modify_command),
                (self.executable, regenerate_command),
            ],
            dryrun,
        )

        if self.production.resolved_dependencies is not None:
            self.production.resolved_dependencies = sorted(
                new_label if name == old_label else name
                for name in self.production.resolved_dependencies
            )

        return cluster_id

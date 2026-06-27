"""Deliver page: render presets, settings, jobs, rendering and quick export.

The render flow is order sensitive. Set the format and codec and render settings
first, then add a render job (it snapshots the current settings into the queue),
then start rendering that job id. Rendering is asynchronous: start_render returns
immediately and the caller polls get_render_status / IsRenderingInProgress to
learn when a job finishes.
"""
from __future__ import annotations

from ..connection import get_project
from ..gate import confirm_required

# Passthrough keys accepted by Resolve's SetRenderSettings, beyond TargetDir and
# CustomName which are always set here. Kept so set_render_settings can validate
# and document what it forwards. See README "Looking up Render Settings".
_SETTINGS_KEYS = (
    "SelectAllFrames",
    "MarkIn",
    "MarkOut",
    "UniqueFilenameStyle",
    "ExportVideo",
    "ExportAudio",
    "FormatWidth",
    "FormatHeight",
    "FrameRate",
    "PixelAspectRatio",
    "VideoQuality",
    "AudioCodec",
    "AudioBitDepth",
    "AudioSampleRate",
    "ColorSpaceTag",
    "GammaTag",
    "ExportAlpha",
    "EncodingProfile",
    "MultiPassEncode",
    "AlphaMode",
    "NetworkOptimization",
    "ClipStartFrame",
    "TimelineStartTimecode",
    "ReplaceExistingFilesInPlace",
)


def list_render_presets() -> dict:
    """List the project's render presets by name. Requires an open project.

    Returns ``{"presets": [...], "count": n}``. Pass a name from this list to
    load_render_preset.
    """
    project = get_project()
    presets = project.GetRenderPresetList() or []
    presets = list(presets)
    return {"presets": presets, "count": len(presets)}


def load_render_preset(name: str) -> dict:
    """Set a render preset as the current render settings. Requires an open project.

    ``name`` must exist in list_render_presets. This replaces the current render
    settings with the preset, so call it before set_render_settings if you also
    want to override target directory or filename. Returns status "done" or
    "failed" (the preset name was not found).
    """
    project = get_project()
    ok = bool(project.LoadRenderPreset(name))
    return {"status": "done" if ok else "failed", "name": name}


def get_render_formats() -> dict:
    """List available render formats mapped to their file extension. Requires an open project.

    Returns ``{"formats": {format: extension, ...}}``. Use a format key with
    get_render_codecs and set_render_format_codec.
    """
    project = get_project()
    formats = project.GetRenderFormats() or {}
    return {"formats": dict(formats)}


def get_render_codecs(render_format: str) -> dict:
    """List available codecs for a render format. Requires an open project.

    ``render_format`` is a format key from get_render_formats. Returns
    ``{"codecs": {description: codec_name, ...}}``; pass a codec_name (the dict
    value) to set_render_format_codec.
    """
    project = get_project()
    codecs = project.GetRenderCodecs(render_format) or {}
    return {"render_format": render_format, "codecs": dict(codecs)}


def set_render_format_codec(render_format: str, codec: str) -> dict:
    """Set the current render format and codec. Requires an open project.

    ``render_format`` is a key from get_render_formats; ``codec`` is a codec name
    (a value) from get_render_codecs for that format. Do this before
    set_render_settings and add_render_job. Returns status plus the now-current
    format and codec as Resolve reports them.
    """
    project = get_project()
    ok = bool(project.SetCurrentRenderFormatAndCodec(render_format, codec))
    current = project.GetCurrentRenderFormatAndCodec() or {}
    return {
        "status": "done" if ok else "failed",
        "requested": {"format": render_format, "codec": codec},
        "current": dict(current),
    }


def set_render_settings(
    target_dir: str, custom_name: str, settings: dict | None = None
) -> dict:
    """Set render output settings (output folder, filename, frame range, etc). Requires an open project.

    Always sets TargetDir (``target_dir``, the output folder) and CustomName
    (``custom_name``, the output filename). ``settings`` is an optional dict of
    further keys passed straight through to Resolve. Supported passthrough keys:
    SelectAllFrames (bool; when True, MarkIn/MarkOut are ignored), MarkIn (int),
    MarkOut (int), UniqueFilenameStyle (0 prefix, 1 suffix), ExportVideo (bool),
    ExportAudio (bool), FormatWidth (int), FormatHeight (int), FrameRate (float,
    e.g. 23.976 or 24), PixelAspectRatio (str), VideoQuality (int or one of
    "Least"/"Low"/"Medium"/"High"/"Best"), AudioCodec (str), AudioBitDepth (int),
    AudioSampleRate (int), ColorSpaceTag (str), GammaTag (str), ExportAlpha
    (bool), EncodingProfile (str, H.264/H.265 only), MultiPassEncode (bool, H.264
    only), AlphaMode (0 premultiplied, 1 straight), NetworkOptimization (bool,
    QuickTime/MP4 only), ClipStartFrame (int), TimelineStartTimecode (str),
    ReplaceExistingFilesInPlace (bool). Unknown keys are dropped and reported.
    Set the format and codec first, then call this, then add_render_job. Returns
    status, the merged settings applied, and any ignored keys.
    """
    project = get_project()

    merged: dict = {"TargetDir": target_dir, "CustomName": custom_name}
    ignored: list[str] = []
    if settings:
        for key, value in settings.items():
            if key in _SETTINGS_KEYS:
                merged[key] = value
            else:
                ignored.append(key)

    ok = bool(project.SetRenderSettings(merged))
    return {
        "status": "done" if ok else "failed",
        "applied": merged,
        "ignored_keys": ignored,
    }


def add_render_job() -> dict:
    """Add a render job to the queue from the current render settings. Requires an open project.

    Snapshots the current timeline plus the current format, codec and render
    settings into a new queued job. Set those first (set_render_format_codec,
    set_render_settings) and make sure a timeline is current. Returns status and
    the new job id, which you pass to start_render, get_render_status and
    delete_render_jobs. A falsy return means Resolve refused to add the job
    (no current timeline or invalid settings).
    """
    project = get_project()
    job_id = project.AddRenderJob()
    if not job_id:
        return {
            "status": "failed",
            "detail": "Resolve did not add a render job. Open a timeline and set "
            "the render format, codec and settings first.",
        }
    return {"status": "done", "job_id": str(job_id)}


def list_render_jobs() -> dict:
    """List the render jobs currently in the queue with their settings. Requires an open project.

    Returns ``{"jobs": [...], "count": n}``. Each job is a dict of Resolve's job
    information (job id, timeline name, output settings). Empty when the queue
    has no jobs.
    """
    project = get_project()
    jobs = project.GetRenderJobList() or []
    jobs = [dict(job) for job in jobs]
    return {"jobs": jobs, "count": len(jobs)}


def start_render(job_ids: list[str] | None = None, confirm: bool = False) -> dict:
    """Start rendering queued jobs. GATED, writes output files and is long running. Requires an open project.

    With ``job_ids`` given, renders only those jobs (from list_render_jobs); with
    it omitted, renders every queued job. Rendering is asynchronous: this returns
    as soon as it starts. Poll get_render_status(job_id) and the
    is_rendering_in_progress flag it reports to learn when jobs finish; use
    stop_render to abort. First call with confirm omitted returns a preview and
    changes nothing.
    """
    project = get_project()

    target = "all queued render jobs" if not job_ids else f"render jobs {job_ids}"
    if not confirm:
        return confirm_required(
            f"start rendering {target}",
            "this writes output files to disk and can take a long time",
            job_ids=job_ids,
        )

    if job_ids:
        ok = bool(project.StartRendering(job_ids))
    else:
        ok = bool(project.StartRendering())

    return {
        "status": "rendering" if ok else "failed",
        "job_ids": job_ids,
        "detail": "Rendering started; poll get_render_status to track progress."
        if ok
        else "Resolve did not start rendering. Check the job ids and that the "
        "queue has renderable jobs.",
    }


def stop_render() -> dict:
    """Stop any render currently in progress. Requires an open project.

    Halts active rendering immediately. Safe to call when nothing is rendering.
    Returns the is_rendering_in_progress flag afterwards.
    """
    project = get_project()
    project.StopRendering()
    return {
        "status": "stopped",
        "is_rendering_in_progress": bool(project.IsRenderingInProgress()),
    }


def get_render_status(job_id: str) -> dict:
    """Report the status and completion of one render job. Requires an open project.

    ``job_id`` comes from add_render_job or list_render_jobs. Returns Resolve's
    status dict for the job (typically a JobStatus and CompletionPercentage) plus
    the project-wide is_rendering_in_progress flag. Poll this after start_render.
    """
    project = get_project()
    status = project.GetRenderJobStatus(job_id) or {}
    return {
        "job_id": job_id,
        "job_status": dict(status),
        "is_rendering_in_progress": bool(project.IsRenderingInProgress()),
    }


def delete_render_jobs(
    job_ids: list[str] | None = None, confirm: bool = False
) -> dict:
    """Delete render jobs from the queue. GATED. Requires an open project.

    With ``job_ids`` given, deletes only those jobs (from list_render_jobs); with
    it omitted, deletes every queued job. This only clears queue entries, it does
    not touch already-rendered files. First call with confirm omitted returns a
    preview and changes nothing. Returns per-id results, or status for the
    delete-all case.
    """
    project = get_project()

    target = "all queued render jobs" if not job_ids else f"render jobs {job_ids}"
    if not confirm:
        return confirm_required(
            f"delete {target}",
            "removes the jobs from the render queue; rendered files are untouched",
            job_ids=job_ids,
        )

    if not job_ids:
        ok = bool(project.DeleteAllRenderJobs())
        return {
            "status": "done" if ok else "failed",
            "scope": "all",
        }

    results = {jid: bool(project.DeleteRenderJob(jid)) for jid in job_ids}
    return {
        "status": "done" if all(results.values()) else "partial",
        "results": results,
    }


def list_quick_export_presets() -> dict:
    """List Quick Export render presets by name. Requires an open project.

    Returns ``{"presets": [...], "count": n}``. Pass a name from this list to
    quick_export.
    """
    project = get_project()
    presets = project.GetQuickExportRenderPresets() or []
    presets = list(presets)
    return {"presets": presets, "count": len(presets)}


def quick_export(
    preset_name: str,
    target_dir: str,
    custom_name: str | None = None,
    confirm: bool = False,
) -> dict:
    """Quick export the current timeline with a built-in preset. GATED, writes a file. Requires an open project and a current timeline.

    ``preset_name`` must be one of list_quick_export_presets. ``target_dir`` is
    the output folder; ``custom_name`` is the optional output filename. This
    renders the current active timeline synchronously and returns Resolve's
    result dict (job status and time taken) or an error string if the render
    failed or was not attempted. First call with confirm omitted returns a
    preview and changes nothing.
    """
    project = get_project()

    if not confirm:
        return confirm_required(
            f"quick export the current timeline with preset '{preset_name}'",
            "this renders the active timeline and writes a file to disk",
            preset_name=preset_name,
            target_dir=target_dir,
            custom_name=custom_name,
        )

    params: dict = {"TargetDir": target_dir}
    if custom_name:
        params["CustomName"] = custom_name

    result = project.RenderWithQuickExport(preset_name, params)
    if isinstance(result, dict):
        return {"status": "done", "preset_name": preset_name, "result": dict(result)}
    return {
        "status": "failed",
        "preset_name": preset_name,
        "detail": str(result) if result else "Quick export did not run.",
    }


def register(mcp) -> None:
    for fn in (
        list_render_presets,
        load_render_preset,
        get_render_formats,
        get_render_codecs,
        set_render_format_codec,
        set_render_settings,
        add_render_job,
        list_render_jobs,
        start_render,
        stop_render,
        get_render_status,
        delete_render_jobs,
        list_quick_export_presets,
        quick_export,
    ):
        mcp.tool()(fn)

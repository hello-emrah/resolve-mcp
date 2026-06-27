<div align="center">

<img src="assets/logo.png" alt="Svetovid" width="160" />

# Svetovid

**An MCP server for seeing and editing video in DaVinci Resolve Studio.**

Svetovid is the four faced Slavic god who watches every direction at once, the all seer. *Svet* is light, *vid* is sight, the same ancient root that gives us the word video. The name signals the one thing most tooling cannot do: see.

<br/>

<a href="https://www.buymeacoffee.com/hello_emrah"><img src="https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee&emoji=%E2%98%95&slug=hello_emrah&button_colour=9686D8&font_colour=3a2a10&coffee_colour=3a2a10&outline_colour=3a2a10&font_family=Inter" alt="Buy me a coffee" height="44" /></a>

</div>

---

Svetovid is a Model Context Protocol server for DaVinci Resolve Studio. Most tools drive an editor blind, pushing metadata they cannot see. Svetovid renders the frame at the playhead and hands it back, so the agent works from what is really on screen, not a guess. It speaks to Resolve over its scripting API, and you and the agent share the same open project. Built for personal use, shared openly, not productised.

Runs on your machine, alongside your open Resolve project.

## Tools

Eighty nine tools spanning the Resolve scripting API, from orienting in a project to delivering the final file. The two at the top are the heart: Svetovid renders the real frame so the agent edits against what is on screen, not blind metadata. Everything destructive sits behind a confirm gate, the tool previews the action and only applies it when called again with `confirm` set, so a first exploratory call never deletes work or starts a render.

| Group | Tools |
|---|---|
| See and navigate | `get_state`, `render_current_frame`, `open_page`, `get_playhead`, `set_playhead_timecode`, `set_playhead_frame`, `get_current_item` |
| Project | `list_projects`, `get_project_info`, `create_project`, `load_project`, `save_project`, `get_project_settings`, `set_project_setting` |
| Media | `browse_storage`, `import_media`, `list_media_pool`, `create_bin`, `set_current_bin`, `get_clip_properties`, `set_clip_property`, `set_clip_mark_in_out`, `delete_media_clips` |
| Timeline | `list_timelines`, `create_empty_timeline`, `set_current_timeline`, `rename_timeline`, `duplicate_timeline`, `delete_timeline`, `get_timeline_settings`, `set_timeline_setting`, `set_timeline_start_timecode`, `add_track`, `delete_track`, `set_track_name`, `set_track_enabled`, `set_track_locked` |
| Edit and assembly | `create_timeline_from_clips`, `append_to_timeline`, `insert_title`, `insert_fusion_title`, `insert_generator`, `create_compound_clip`, `create_fusion_clip`, `detect_scene_cuts`, `delete_timeline_items` |
| Clip transforms | `list_timeline_items`, `get_item_properties`, `set_item_property`, `set_item_transform`, `set_item_enabled`, `set_item_clip_color`, `smart_reframe`, `stabilize`, `add_fusion_comp` |
| Markers | `add_marker`, `list_markers`, `delete_marker`, `delete_markers_by_color` |
| Colour | `list_color_groups`, `add_color_group`, `assign_to_color_group`, `get_node_graph_info`, `set_node_lut`, `set_node_enabled`, `set_cdl`, `copy_grade`, `reset_grades`, `grab_still` |
| Audio | `insert_audio_at_playhead`, `transcribe_audio`, `clear_transcription`, `set_voice_isolation`, `create_subtitles_from_audio`, `auto_sync_audio` |
| Render and deliver | `list_render_presets`, `load_render_preset`, `get_render_formats`, `get_render_codecs`, `set_render_format_codec`, `set_render_settings`, `add_render_job`, `list_render_jobs`, `start_render`, `stop_render`, `get_render_status`, `delete_render_jobs`, `list_quick_export_presets`, `quick_export` |

Every tool returns plain data the agent can read, and reaches Resolve through the shared scaffolding in `connection.py` (the live handle), `gate.py` (the confirm gate) and `serialize.py` (objects to plain dicts). One module per group under `src/svetovid/tools/`.

## Requirements

- DaVinci Resolve **Studio** 18.5 or newer, running. The scripting API is Studio only.
- External scripting enabled: Resolve, Preferences, System, General, **External scripting using** set to **Local**.
- Python 3.10 or newer.

## Install

```bash
git clone https://github.com/hello-emrah/svetovid-mcp.git
cd svetovid-mcp
pip install -e .
```

## Wire into Claude Code

Add an entry to `~/.claude.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "svetovid": {
      "command": "svetovid-mcp"
    }
  }
}
```

Restart Claude Code. The tools appear under the `mcp__svetovid__*` namespace.

## Environment

Resolve's scripting paths are auto-detected per platform. Set `RESOLVE_SCRIPT_API` and `RESOLVE_SCRIPT_LIB` in a `.env` only for a non-standard install (see `.env.example`).

## Why "Svetovid"

Svetovid stood on the island of Rügen as a four faced idol, looking north, south, east and west so nothing could pass him unseen, the god of light, sight and divination. The name carries the whole idea of this tool: an editor the agent can see through, watching the timeline from every side. And the root underneath it, *vid*, to see, is the same one that surfaces in the word video.

## Design philosophy

The visual mark and the tool itself were built deliberately against the visual language of capitalist software design. No gradients, no neon, no glass, no drop shadows, no isometric stock illustration. Single-shade flat seals in warm earth tones, ancient-glyph silhouettes, generous whitespace. The mark could be pressed into wax or carved into stone.

This tool is built for personal use and shared openly. It is not productised, monetised, or instrumented. Use it for your own work or fork it for yours.

## License

MIT, see [LICENSE](LICENSE).

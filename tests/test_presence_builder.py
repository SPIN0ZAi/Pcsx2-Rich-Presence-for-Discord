"""
Tests for the PresenceBuilder — payload construction and smart diffing.
"""
from __future__ import annotations

import time
import pytest

from detection.detector import GameState, PCSX2State
from metadata.metadata_manager import GameInfo
from discord_rpc.presence import PresenceBuilder, PresencePayload
from utils.config import PresenceConfig, ButtonConfig


def _make_config(**kwargs) -> PresenceConfig:
    return PresenceConfig(**kwargs)


def _game_info(
    serial: str = "SLUS-21548",
    title: str = "God of War II",
    cover_url: str | None = "https://images.igdb.com/cover.jpg",
    igdb_url: str | None = "https://www.igdb.com/games/god-of-war-ii",
) -> GameInfo:
    return GameInfo(
        serial=serial,
        title=title,
        cover_url=cover_url,
        igdb_url=igdb_url,
        summary=None,
        year=2007,
        region="USA",
        source="igdb",
    )


def _playing_state(serial: str = "SLUS-21548", session_start: float | None = None) -> GameState:
    return GameState(
        state=PCSX2State.PLAYING,
        serial=serial,
        game_title="God of War II",
        session_start=session_start or time.time(),
    )


class TestPresenceBuilder:

    def test_stopped_returns_none(self):
        builder = PresenceBuilder(_make_config())
        info = _game_info()
        state = GameState(state=PCSX2State.STOPPED)
        payload = builder.build(state, info)
        assert payload is None

    def test_playing_sets_details(self):
        builder = PresenceBuilder(_make_config())
        info = _game_info()
        state = _playing_state()
        payload = builder.build(state, info)
        assert payload is not None
        assert "God of War II" in payload.details

    def test_privacy_mode_hides_title(self):
        cfg = _make_config(privacy_mode=True)
        builder = PresenceBuilder(cfg)
        info = _game_info()
        state = _playing_state()
        payload = builder.build(state, info)
        assert payload is not None
        assert "God of War II" not in payload.details
        assert "PS2" in payload.details

    def test_privacy_mode_hides_igdb_button(self):
        cfg = _make_config(
            privacy_mode=True,
            buttons=[ButtonConfig(label="View on IGDB", enabled=True)],
        )
        builder = PresenceBuilder(cfg)
        info = _game_info()
        state = _playing_state()
        payload = builder.build(state, info)
        assert not payload.buttons  # buttons suppressed in privacy mode

    def test_igdb_button_added_when_url_available(self):
        cfg = _make_config(buttons=[ButtonConfig(label="View on IGDB", enabled=True)])
        builder = PresenceBuilder(cfg)
        info = _game_info(igdb_url="https://www.igdb.com/games/god-of-war-ii")
        state = _playing_state()
        payload = builder.build(state, info)
        assert any(b["label"] == "View on IGDB" for b in payload.buttons)

    def test_no_igdb_button_when_url_missing(self):
        cfg = _make_config(buttons=[ButtonConfig(label="View on IGDB", enabled=True)])
        builder = PresenceBuilder(cfg)
        info = _game_info(igdb_url=None)
        state = _playing_state()
        payload = builder.build(state, info)
        assert not payload.buttons

    def test_cover_url_used_as_large_image(self):
        cfg = _make_config(show_cover_art=True)
        builder = PresenceBuilder(cfg)
        info = _game_info(cover_url="https://images.igdb.com/cover.jpg")
        state = _playing_state()
        payload = builder.build(state, info)
        assert payload.large_image == "https://images.igdb.com/cover.jpg"

    def test_default_image_when_no_cover(self):
        cfg = _make_config(show_cover_art=True)
        builder = PresenceBuilder(cfg)
        info = _game_info(cover_url=None)
        state = _playing_state()
        payload = builder.build(state, info)
        assert payload.large_image == "ps2_default"

    def test_small_image_always_ps2_logo(self):
        builder = PresenceBuilder(_make_config())
        payload = builder.build(_playing_state(), _game_info())
        assert payload.small_image == "ps2_logo"

    def test_paused_state_string(self):
        builder = PresenceBuilder(_make_config())
        state = GameState(state=PCSX2State.PAUSED, serial="SLUS-21548", game_title="Test")
        payload = builder.build(state, _game_info())
        assert payload.state == "Paused"

    def test_elapsed_time_set_when_session_start_provided(self):
        cfg = _make_config(show_elapsed_time=True)
        builder = PresenceBuilder(cfg)
        session_start = time.time() - 300  # 5 minutes ago
        state = _playing_state(session_start=session_start)
        payload = builder.build(state, _game_info())
        assert payload.start == int(session_start)

    def test_no_elapsed_time_when_disabled(self):
        cfg = _make_config(show_elapsed_time=False)
        builder = PresenceBuilder(cfg)
        state = _playing_state(session_start=time.time())
        payload = builder.build(state, _game_info())
        assert payload.start is None

    def test_smart_diff_suppresses_duplicate_update(self):
        builder = PresenceBuilder(_make_config())
        state = _playing_state()
        info = _game_info()
        # First build — should return payload
        first = builder.build(state, info)
        assert first is not None
        # Second identical build — should return None (no change)
        second = builder.build(state, info)
        assert second is None

    def test_force_clear_resets_diff(self):
        builder = PresenceBuilder(_make_config())
        state = _playing_state()
        info = _game_info()
        builder.build(state, info)  # prime the diff cache
        builder.force_clear()
        # Next build should be sent even though state is the same
        payload = builder.build(state, info)
        assert payload is not None

    def test_to_kwargs_contains_expected_keys(self):
        builder = PresenceBuilder(_make_config())
        payload = builder.build(_playing_state(), _game_info())
        kwargs = payload.to_kwargs()
        assert "details" in kwargs
        assert "state" in kwargs
        assert "large_image" in kwargs
        assert "small_image" in kwargs

from dataclasses import replace
from config import Settings
from db.store import Store


def _store(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    s.create_all()
    return s


def test_get_settings_initializes_defaults(tmp_path):
    s = _store(tmp_path)
    settings = s.get_settings()
    assert isinstance(settings, Settings)
    assert settings.short_period == Settings().short_period
    assert settings.max_volume_pct == 0.01


def test_save_and_get_roundtrip(tmp_path):
    s = _store(tmp_path)
    s.get_settings()  # 초기화
    modified = replace(Settings(), short_period=7, trailing_stop_pct=0.15,
                       max_volume_pct=0.02, min_trade_value_krw=5_000_000_000.0)
    s.save_settings(modified)
    loaded = s.get_settings()
    assert loaded.short_period == 7
    assert loaded.trailing_stop_pct == 0.15
    assert loaded.max_volume_pct == 0.02
    assert loaded.min_trade_value_krw == 5_000_000_000.0

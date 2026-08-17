from dataclasses import replace
from config import Settings
from db.store import Store


def test_live_settings_defaults(tmp_path):
    s = Store(str(tmp_path / "ls.db")); s.create_all()
    cfg = s.get_settings()
    assert cfg.live_enabled is False
    assert cfg.max_invest_krw == 300000.0
    assert cfg.daily_loss_limit_pct == 0.05
    assert cfg.kill_switch is False


def test_live_settings_roundtrip(tmp_path):
    s = Store(str(tmp_path / "ls.db")); s.create_all()
    s.get_settings()
    s.save_settings(replace(Settings(), live_enabled=True, kill_switch=True,
                            max_invest_krw=100000.0, daily_loss_limit_pct=0.03))
    got = s.get_settings()
    assert got.live_enabled is True and got.kill_switch is True
    assert got.max_invest_krw == 100000.0 and got.daily_loss_limit_pct == 0.03

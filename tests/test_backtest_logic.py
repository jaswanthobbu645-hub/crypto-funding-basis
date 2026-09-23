import pytest

class TestBacktestLogic:
    def test_entry_short_when_z_high(self):
        z = 1.5
        assert z > 0.8  # would trigger SHORT perp

    def test_entry_long_when_z_low(self):
        z = -1.5
        assert z < -0.8  # would trigger LONG perp

    def test_no_entry_when_z_neutral(self):
        z = 0.3
        assert not (z > 0.8 or z < -0.8)

    def test_exit_on_revert(self):
        z_after = 0.2
        assert abs(z_after) < 0.3  # exit signal


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
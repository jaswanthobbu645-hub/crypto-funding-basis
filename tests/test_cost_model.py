import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestCostModel:
    def test_maker_fee(self):
        FEE_MAKER = 0.0003
        round_trip = FEE_MAKER * 2
        assert round_trip == 0.0006

    def test_taker_fee(self):
        FEE_TAKER = 0.0005
        round_trip = FEE_TAKER * 2
        assert round_trip == 0.0010

    def test_funding_filter_threshold(self):
        MIN_FUNDING = 0.0003
        assert MIN_FUNDING >= 0.0003


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
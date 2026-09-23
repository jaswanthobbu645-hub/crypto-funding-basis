import sys
import os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.strategy.multi_asset import compute_zscore


class TestZScore:
    def test_zscore_mean_zero(self):
        s = pd.Series(np.random.randn(1000))
        z = compute_zscore(s, 100)
        assert abs(z.dropna().mean()) < 0.5

    def test_zscore_std_one(self):
        s = pd.Series(np.random.randn(2000))
        z = compute_zscore(s, 200)
        assert abs(z.dropna().std() - 1.0) < 0.3

    def test_zscore_constant_series(self):
        s = pd.Series([0.001] * 100)
        z = compute_zscore(s, 20)
        assert z.dropna().abs().max() < 10

    def test_zscore_extreme_shock(self):
        s = pd.Series([0.0] * 100 + [1.0])
        z = compute_zscore(s, 50)
        assert z.iloc[-1] > 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
import numpy as np
from toyattn import scaled_dot_product


def test_scaled_dot_product_shape_and_finite():
    rng = np.random.default_rng(0)
    q = rng.normal(size=(2, 3, 4, 8))
    k = rng.normal(size=(2, 3, 4, 8))
    v = rng.normal(size=(2, 3, 4, 8))
    out = scaled_dot_product(q, k, v)
    assert out.shape == v.shape
    assert np.isfinite(out).all()

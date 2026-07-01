from lot_reconciler.numeric_utils import to_float, values_equal


def test_to_float_handles_various_formats():
    assert to_float(None) is None
    assert to_float("") is None
    assert to_float(10) == 10.0
    assert to_float(10.5) == 10.5
    assert to_float("1 234,56") == 1234.56
    assert to_float("1234.56") == 1234.56
    assert to_float("abc") is None


def test_values_equal_numeric_tolerance():
    assert values_equal(100, 100.0)
    assert values_equal("1 000,00", 1000)
    assert not values_equal(100, 101)


def test_values_equal_text_normalization():
    assert values_equal(" Астана ", "астана")
    assert values_equal(None, "")
    assert not values_equal("Астана", "Алматы")

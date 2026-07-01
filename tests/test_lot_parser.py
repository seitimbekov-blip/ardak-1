from lot_reconciler.lot_parser import parse_lot_number


def test_parses_base_version_zero():
    ident = parse_lot_number("56/100 Т")
    assert ident.base_number == "56/100"
    assert ident.version == 0
    assert ident.kind == "Т"
    assert ident.key == ("56/100", "Т")
    assert not ident.has_anomaly


def test_parses_versioned_lot():
    ident = parse_lot_number("29/20-1 Т")
    assert ident.base_number == "29/20"
    assert ident.version == 1
    assert ident.kind == "Т"


def test_parses_higher_version():
    ident = parse_lot_number("56/100-2 Т")
    assert ident.base_number == "56/100"
    assert ident.version == 2
    assert ident.kind == "Т"


def test_kind_rabota_and_usluga():
    assert parse_lot_number("1/1 Р").kind == "Р"
    assert parse_lot_number("1/1 У").kind == "У"


def test_missing_kind_flagged():
    ident = parse_lot_number("10/5")
    assert ident.base_number == "10/5"
    assert ident.kind is None
    assert ident.missing_kind is True
    assert ident.has_anomaly is True


def test_unparsable_value():
    ident = parse_lot_number("не номер лота")
    assert ident.base_number is None
    assert ident.parse_error is not None
    assert ident.key is None


def test_empty_value():
    ident = parse_lot_number(None)
    assert ident.parse_error is not None
    ident2 = parse_lot_number("   ")
    assert ident2.parse_error is not None


def test_extra_whitespace_and_dot_tolerated():
    ident = parse_lot_number(" 25/480  Т. ")
    assert ident.base_number == "25/480"
    assert ident.kind == "Т"

from engine.symbol_utils import canonicalize_tradingsymbol, tradingsymbols_equal


def test_canonicalizes_direction_prefix_format():
    assert canonicalize_tradingsymbol("NIFTY25NOV25C26100") == "NIFTY25NOV2526100CE"


def test_canonicalizes_direction_suffix_missing_e():
    assert canonicalize_tradingsymbol("NIFTY25NOV2526100P") == "NIFTY25NOV2526100PE"


def test_returns_existing_canonical_symbol():
    symbol = "NIFTY25NOV2526100CE"
    assert canonicalize_tradingsymbol(symbol) == symbol


def test_tradingsymbols_equal_handles_variants():
    assert tradingsymbols_equal("NIFTY25NOV25C26100", "NIFTY25NOV2526100CE")
    assert not tradingsymbols_equal("NIFTY25NOV25C26100", "BANKNIFTY25NOV2526100CE")


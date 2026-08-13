"""Tier 3 — what is actually in the database. Needs PostgreSQL.

The rule the whole project rests on is that a missing observation is NULL, never
zero and never carried forward. These tests read the loaded data and check that
the rule survived the pipeline, rather than trusting that the loader meant well.
"""

from __future__ import annotations

import pytest


def _rows(db, sql, params=None):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        return cur.fetchall()


def _one(db, sql, params=None):
    return _rows(db, sql, params)[0][0]


# --- the load landed --------------------------------------------------------


def test_the_expected_volume_of_observations_is_present(db):
    total = _one(db, "SELECT count(*) FROM analytics.v_mcp_observation")
    assert total > 200_000, f"only {total} observations visible"


def test_every_dataset_is_represented(db):
    keys = {r[0] for r in _rows(db, "SELECT DISTINCT data_key FROM analytics.v_mcp_series_catalogue")}
    assert {"daily_treasury_yield_curve", "daily_treasury_bill_rates",
            "daily_treasury_real_yield_curve"} <= keys


def test_the_catalogue_is_populated(db):
    assert _one(db, "SELECT count(*) FROM analytics.v_mcp_series_catalogue") >= 40


# --- the NULL rule ----------------------------------------------------------


def test_no_observation_row_carries_a_null_rate(db):
    """The curated view excludes placeholders; a NULL here is a leak."""
    nulls = _one(db, "SELECT count(*) FROM analytics.v_mcp_observation WHERE rate_percent IS NULL")
    assert nulls == 0


def test_the_placeholder_series_is_unreachable_through_the_read_surface(db):
    """BC_30YEARDISPLAY is a literal 0 on 5,256 dates - never a yield."""
    leaked = _one(db, """
        SELECT count(*) FROM analytics.v_mcp_observation
        WHERE series_code = 'BC_30YEARDISPLAY'
    """)
    assert leaked == 0


def test_genuine_zero_rates_are_preserved(db):
    """Short tenors really printed 0.00% in 2008-12, 2011, 2015 and 2020-21.

    The mirror image of the test above: over-zealous placeholder filtering would
    delete real observations, which is just as wrong as inventing them.
    """
    zeros = _one(db, """
        SELECT count(*) FROM analytics.v_mcp_observation
        WHERE rate_percent = 0 AND series_code <> 'BC_30YEARDISPLAY'
    """)
    assert zeros > 0, "real 0.00% prints appear to have been filtered away"


# --- semantics travel with the data -----------------------------------------


def test_every_catalogued_series_declares_a_quoting_basis(db):
    missing = _one(db, """
        SELECT count(*) FROM analytics.v_mcp_series_catalogue
        WHERE quote_basis IS NULL OR btrim(quote_basis) = ''
    """)
    assert missing == 0


def test_every_catalogued_series_declares_a_rate_kind(db):
    missing = _one(db, """
        SELECT count(*) FROM analytics.v_mcp_series_catalogue
        WHERE rate_kind IS NULL OR btrim(rate_kind) = ''
    """)
    assert missing == 0


def test_quoting_bases_are_drawn_from_the_known_set(db):
    """An unrecognised basis downstream is a rate nobody can interpret."""
    found = {r[0] for r in _rows(db, "SELECT DISTINCT quote_basis FROM analytics.v_mcp_series_catalogue")}
    known = {"par_coupon_semiannual", "bank_discount_act360",
             "coupon_equivalent", "average_real_yield"}
    assert found <= known, f"unknown quoting basis: {found - known}"


def test_bill_discount_rates_and_par_yields_do_not_share_a_basis(db):
    """The trap this project exists to prevent."""
    bases = {r[0] for r in _rows(db, """
        SELECT DISTINCT quote_basis FROM analytics.v_mcp_series_catalogue
        WHERE data_key = 'daily_treasury_bill_rates'
    """)}
    assert "par_coupon_semiannual" not in bases


# --- coverage is honest -----------------------------------------------------


def test_series_coverage_bounds_are_ordered(db):
    """first_observation must never post-date last_observation."""
    broken = _one(db, """
        SELECT count(*) FROM analytics.v_mcp_series_catalogue
        WHERE first_observation IS NOT NULL AND last_observation IS NOT NULL
          AND first_observation > last_observation
    """)
    assert broken == 0


def test_the_thirty_year_gap_is_real_and_still_visible(db):
    """The bond was discontinued 2002 and reintroduced 2006.

    A pipeline that quietly interpolated across it would show continuous
    coverage - which is exactly the defect that must stay detectable.
    """
    present = _one(db, """
        SELECT count(*) FROM analytics.v_mcp_observation
        WHERE series_code = 'BC_30YEAR'
          AND observation_date BETWEEN DATE '2003-06-01' AND DATE '2005-06-01'
    """)
    assert present == 0, "the 30-year hole has been filled in from somewhere"


def test_no_observation_predates_the_published_history(db):
    earliest = _one(db, "SELECT min(observation_date) FROM analytics.v_mcp_observation")
    assert earliest.year >= 1990


def test_no_observation_is_in_the_future(db):
    import datetime as dt
    latest = _one(db, "SELECT max(observation_date) FROM analytics.v_mcp_observation")
    assert latest <= dt.date.today()


# --- the privilege boundary -------------------------------------------------


def test_the_reader_identity_is_constrained(db):
    """The MCP data server must connect as a role that cannot write."""
    from mcp_servers.data._db import assert_constrained_identity
    with db() as conn:
        assert_constrained_identity(conn)  # raises if the role is over-privileged


def test_the_reader_cannot_see_the_raw_schemas(db):
    """`mcp_reader` has REVOKE on treasury and staging; only analytics is visible."""
    for schema in ("treasury", "staging"):
        with pytest.raises(Exception):
            _rows(db, f"SELECT * FROM {schema}.observation LIMIT 1")


def test_the_reader_cannot_write(db):
    with pytest.raises(Exception):
        _rows(db, "CREATE TABLE analytics.qa_should_not_exist (x int)")

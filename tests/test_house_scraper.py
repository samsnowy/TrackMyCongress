import pandas as pd

from congress.scraper import (
    _dedupe_amended_filings,
    _parse_collapsed_transaction,
)


META = {
    "name": "Test Member",
    "state_dst": "ZZ00",
    "doc_id": "123",
    "filing_date": "7/23/2026",
}


def test_collapsed_stock_without_owner():
    row = (
        "Space Exploration Technologies Corp. - Class A Common Stock "
        "(SPCX) [ST] P 06/18/2026 07/02/2026 $1,001 - $15,000"
    )
    trade = _parse_collapsed_transaction(row, META)
    assert trade["ticker"] == "SPCX"
    assert trade["asset_code"] == "ST"
    assert trade["owner"] == ""


def test_collapsed_other_asset_with_owner():
    row = (
        "SP Space Exploration Technologies Corp. (SPCX) [OT] "
        "P 06/12/2026 06/12/2026 $15,001 - $50,000 "
        "D: Purchase of SPCX public stock."
    )
    trade = _parse_collapsed_transaction(row, META)
    assert trade["ticker"] == "SPCX"
    assert trade["asset_code"] == "OT"
    assert trade["owner"] == "SP"


def test_collapsed_amended_other_asset_with_numeric_id():
    row = (
        "2000164887 SpaceX (SPCX) [OT] P 06/15/2026 06/22/2026 "
        "$50,001 - $100,000 F S: Amended"
    )
    trade = _parse_collapsed_transaction(row, META)
    assert trade["company"] == "SpaceX"
    assert trade["ticker"] == "SPCX"
    assert trade["asset_code"] == "OT"


def test_amendment_dedupe_keeps_newest_document():
    rows = pd.DataFrame([
        {
            "name": "Test Member", "owner": "", "ticker": "SPCX",
            "transaction": "Purchase", "transaction_date": "06/15/2026",
            "notification_date": "06/17/2026",
            "amount_range": "$50,001 - $100,000", "doc_id": "20022577",
        },
        {
            "name": "Test Member", "owner": "", "ticker": "SPCX",
            "transaction": "Purchase", "transaction_date": "06/15/2026",
            "notification_date": "06/22/2026",
            "amount_range": "$50,001 - $100,000", "doc_id": "20035042",
        },
    ])
    result = _dedupe_amended_filings(rows)
    assert result["doc_id"].tolist() == ["20035042"]

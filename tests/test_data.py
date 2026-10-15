import numpy as np
import pandas as pd
import zipfile
import pytest
from orderflow.data import ofi_events, grid_bin, aggregate_day


def test_ofi_price_moves_and_size_changes():
    assert ofi_events([100], [12], [101], [6], (100, 10, 101, 5))[0] == 1
    assert ofi_events([101], [12], [102], [6], (100, 10, 101, 5))[0] == 17
    assert ofi_events([99], [12], [100], [6], (100, 10, 101, 5))[0] == -16


def test_ofi_chunk_boundary_is_invariant():
    b, qb, a, qa = np.array([100,100,101]), np.array([10,12,8]), np.array([101,101,102]), np.array([7,5,4])
    whole = ofi_events(b,qb,a,qa)
    parts = np.r_[ofi_events(b[:2],qb[:2],a[:2],qa[:2]),ofi_events(b[2:],qb[2:],a[2:],qa[2:],(b[1],qb[1],a[1],qa[1]))]
    np.testing.assert_array_equal(whole,parts)


def test_ceiling_bins_never_observe_future():
    np.testing.assert_array_equal(grid_bin([0,1,999,1000,1001],0),[0,1,1,1,2])


def test_real_schema_aggregation_preserves_same_timestamp_and_trade_sign(tmp_path):
    start = 1704067200000
    books = pd.DataFrame({"update_id":[1,2,3],"best_bid_price":[100,100,100],"best_bid_qty":[10,12,15],"best_ask_price":[101,101,101],"best_ask_qty":[10,10,10],"transaction_time":[start+10,start+10,start+1500],"event_time":[start+20,start+20,start+1501]})
    trades = pd.DataFrame({"agg_trade_id":[1,2],"price":[100,101],"quantity":[3,4],"first_trade_id":[1,2],"last_trade_id":[1,2],"transact_time":[start+10,start+1010],"is_buyer_maker":[True,False]})
    for name, frame in [("book",books),("trade",trades)]:
        with zipfile.ZipFile(tmp_path/f"{name}.zip","w") as z: z.writestr(f"{name}.csv",frame.to_csv(index=False))
    one, audit = aggregate_day(tmp_path/"book.zip",tmp_path/"trade.zip","TEST","2024-01-01",chunk_size=1)
    assert np.isnan(one.iloc[0].bid)
    assert one.iloc[1].bid_qty == 12
    assert one.iloc[1].ofi == 2
    assert one.iloc[1].quote_updates == 2
    assert one.iloc[1].signed_trade_qty == 0
    assert one.iloc[2].signed_trade_qty == -3
    assert one.iloc[3].signed_trade_qty == 4
    assert one.iloc[2].quote_age_ms == 499
    assert audit["book_rows"] == 3


def test_interleaved_archive_must_be_sorted_not_filtered(tmp_path):
    from orderflow.data import UnorderedArchive, sort_book_archive
    start = 1704067200000
    book = pd.DataFrame({"update_id":[1,3,2,3], "best_bid_price":[100]*4,
        "best_bid_qty":[10,15,12,15], "best_ask_price":[101]*4,
        "best_ask_qty":[10]*4, "transaction_time":[start+10,start+2010,start+1010,start+2010],
        "event_time":[start+20,start+2020,start+1020,start+2020]})
    trades = pd.DataFrame({"agg_trade_id":[1],"price":[100],"quantity":[1],
        "first_trade_id":[1],"last_trade_id":[1],"transact_time":[start+10],"is_buyer_maker":[True]})
    for name, frame in [("book",book),("trade",trades)]:
        with zipfile.ZipFile(tmp_path/f"{name}.zip","w") as z: z.writestr(f"{name}.csv",frame.to_csv(index=False))
    for chunk_size in [1,100]:
        with pytest.raises(UnorderedArchive):
            aggregate_day(tmp_path/'book.zip',tmp_path/'trade.zip','TEST','2024-01-01',chunk_size=chunk_size)
    audit = sort_book_archive(tmp_path/'book.zip',tmp_path/'sorted.parquet')
    assert audit['exact_duplicate_rows_removed'] == 1
    one,_=aggregate_day(tmp_path/'sorted.parquet',tmp_path/'trade.zip','TEST','2024-01-01',chunk_size=1)
    many,_=aggregate_day(tmp_path/'sorted.parquet',tmp_path/'trade.zip','TEST','2024-01-01',chunk_size=100)
    pd.testing.assert_frame_equal(one,many)
    assert one.iloc[2].bid_qty == 12
    assert one.iloc[3].bid_qty == 15

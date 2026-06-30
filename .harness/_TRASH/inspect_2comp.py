from ingestion.orchestration.cross_source_dedup import cluster_records


def rec(rt, sid, url, title):
    return {"record_type": rt, "source_id": sid, "source_url_or_evidence": url,
            "title_or_label": title, "published_at_or_observed_at": "2025-06-02"}


accA = "0001193125-26-000111"
accB = "0001193125-26-000222"
t = "Grid operator declares regional emergency"
A = [rec("community_signal", "hn", f"https://hn.example.com/{accA}", t),
     rec("community_signal", "reddit", f"https://reddit.example.com/{accA}", t),
     rec("official_record", "sec1", f"https://sec.gov/Archives/{accB}", t),
     rec("official_record", "sec2", f"https://sec.gov/data/{accB}", t)]
B = list(reversed(A))
for name, recs in [("A", A), ("B", B)]:
    cs = cluster_records(recs)
    for c in cs:
        print(name, "n=", len(cs), "conf=", c.confidence, "clique=", c.clique_ok,
              "weak_only=", len(c.weak_only_members), "cid=", c.cluster_id[:30])

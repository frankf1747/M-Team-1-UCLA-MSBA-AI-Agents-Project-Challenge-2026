from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict, Any, Tuple, List
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def reconcile_shipments(df: pd.DataFrame, master_dir: str) -> Dict[str, Any]:
    """Apply playbook DQ rules + Appendix A reconciliation.

    Precedence (playbook Appendix A.6): exact -> alias -> legacy -> unresolved.
    Returns {"valid": DataFrame, "excluded": DataFrame, "stats": dict}.
    """
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    canon = pd.read_csv(os.path.join(master_dir, "item_master_canonical.csv"))
    alias = pd.read_csv(os.path.join(master_dir, "item_alias.csv"))
    legacy = pd.read_csv(os.path.join(master_dir, "item_legacy_map.csv"))

    canon_by_idname = {
        (str(r.item_id).strip(), str(r.canonical_item_name).strip()): r.canonical_item_id
        for r in canon.itertuples()
    }
    alias_by_name = {str(r.alias_name).strip(): r.canonical_item_id for r in alias.itertuples()}
    legacy_by_id = {str(r.legacy_item_id).strip(): r.canonical_item_id for r in legacy.itertuples()}
    temp_by_canon = dict(zip(canon.canonical_item_id, canon.temp_control))

    valid_rows: List[dict] = []
    excluded_rows: List[dict] = []
    seen_uid: set = set()

    for rec in df.to_dict("records"):
        uid = rec.get("unique_item_id")
        if _blank(uid):  # DQ-01
            excluded_rows.append({**rec, "reason": "missing_unique_item_id"})
            continue
        if str(uid).strip() in seen_uid:  # DQ-04
            excluded_rows.append({**rec, "reason": "duplicate_unique_item_id"})
            continue
        seen_uid.add(str(uid).strip())

        iid = str(rec.get("item_id")).strip()
        iname = str(rec.get("item_name")).strip()

        canonical_id, reason = None, None
        if (iid, iname) in canon_by_idname:           # D3 exact
            canonical_id, reason = canon_by_idname[(iid, iname)], "exact_match"
        elif iname in alias_by_name:                  # D4 alias
            canonical_id, reason = alias_by_name[iname], "alias_match"
        elif iid in legacy_by_id:                     # D5 legacy
            canonical_id, reason = legacy_by_id[iid], "legacy_id_map"

        if canonical_id is None:                      # D6 unresolved
            excluded_rows.append({**rec, "reason": "excluded_unresolved"})
            continue

        valid_rows.append({
            **rec,
            "canonical_item_id": canonical_id,
            "temp_control": temp_by_canon.get(canonical_id, "Room Temp (20-25C)"),
            "reason": reason,
        })

    valid = pd.DataFrame(valid_rows)
    excluded = pd.DataFrame(excluded_rows)
    stats = {
        "input_rows": int(len(df)),
        "valid_rows": int(len(valid)),
        "excluded_rows": int(len(excluded)),
        "excluded_by_reason": (
            excluded["reason"].value_counts().to_dict() if not excluded.empty else {}
        ),
        "fixed_by_reason": (
            valid["reason"].value_counts().to_dict() if not valid.empty else {}
        ),
    }
    return {"valid": valid, "excluded": excluded, "stats": stats}


@dataclass
class CsvAnalysisResult:
    summary: Dict[str, Any]
    kpis: Dict[str, Any]
    anomalies: pd.DataFrame
    cleaned_shape: Tuple[int, int]
    numeric_cols: List[str]


def analyze_csv(csv_path: str) -> CsvAnalysisResult:
    df = pd.read_csv(csv_path)
    original_shape = df.shape

    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(how="all").copy()

    # Try to parse any column that looks like a date
    for c in df.columns:
        if "date" in c.lower() or "time" in c.lower():
            try:
                df[c] = pd.to_datetime(df[c], errors="ignore")
            except Exception:
                pass

    summary = {
        "rows_original": int(original_shape[0]),
        "cols_original": int(original_shape[1]),
        "rows_after_drop_empty": int(df.shape[0]),
        "missingness_top": df.isna().mean().sort_values(ascending=False).head(10).to_dict(),
        "column_dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "columns": list(df.columns),
    }

    # Generic KPI examples: you will tailor later once we see headers
    kpis: Dict[str, Any] = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if numeric_cols:
        kpis["numeric_columns_count"] = len(numeric_cols)
        kpis["rows_count"] = int(df.shape[0])

    # Anomalies on numeric cols
    anomalies = pd.DataFrame()
    if len(numeric_cols) >= 2 and df.shape[0] >= 20:
        X = df[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        model = IsolationForest(
            n_estimators=200,
            contamination=0.03,
            random_state=42,
        )
        preds = model.fit_predict(X)
        scores = model.decision_function(X)

        df_anom = df.copy()
        df_anom["is_anomaly"] = (preds == -1)
        df_anom["anomaly_score"] = scores

        anomalies = df_anom[df_anom["is_anomaly"]].sort_values("anomaly_score").head(25)

    return CsvAnalysisResult(
        summary=summary,
        kpis=kpis,
        anomalies=anomalies,
        cleaned_shape=df.shape,
        numeric_cols=numeric_cols,
    )

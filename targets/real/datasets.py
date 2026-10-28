"""Real public datasets for R3 targets.

Two datasets, both downloaded from the UCI Machine Learning Repository and
cached under ``data/real/``:

- ``uci_credit_default``: Default of Credit Card Clients (UCI id 350).
- ``adult_income``: Adult (UCI id 2).

Nothing here synthesises rows. If a download fails and no cache exists, the
loader raises ``DatasetUnavailable`` with the exact URL, the exact destination
path, and the extraction layout, so the data can be placed by hand.

The cache has two layers:

1. ``data/real/raw/`` holds the original archives. It is git-ignored.
2. ``data/real/<name>.csv`` holds the canonicalised frame used by training.
   It is committed, so training and tests run offline and reproducibly.

The CSVs keep the dataset's own columns and label. Canonical applicant mapping
lives in ``targets/real/features.py`` and is documented in
``targets/real/README.md``.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from config_loader import REPO_ROOT

DATA_DIR = REPO_ROOT / "data" / "real"
RAW_DIR = DATA_DIR / "raw"

CREDIT_URL = (
    "https://archive.ics.uci.edu/static/public/350/"
    "default+of+credit+card+clients.zip"
)
ADULT_URL = "https://archive.ics.uci.edu/static/public/2/adult.zip"

CREDIT_ARCHIVE = "credit.zip"
ADULT_ARCHIVE = "adult.zip"
CREDIT_CSV = "uci_credit_default.csv"
ADULT_CSV = "adult_income.csv"

CREDIT_XLS = "default of credit card clients.xls"
ADULT_DATA = "adult.data"


@dataclass(frozen=True)
class DatasetInfo:
    name: str
    url: str
    csv_name: str
    archive_name: str
    raw_members: tuple[str, ...]
    citation: str
    license: str
    doi: str


DATASETS: dict[str, DatasetInfo] = {
    "uci_credit_default": DatasetInfo(
        name="uci_credit_default",
        url=CREDIT_URL,
        csv_name=CREDIT_CSV,
        archive_name=CREDIT_ARCHIVE,
        raw_members=(CREDIT_XLS,),
        citation=(
            "Yeh, I. C., & Lien, C. H. (2009). The comparisons of data mining "
            "techniques for the predictive accuracy of probability of default "
            "of credit card clients. Expert Systems with Applications, 36(2), "
            "2473-2480."
        ),
        license="CC BY 4.0",
        doi="10.24432/C55S3H",
    ),
    "adult_income": DatasetInfo(
        name="adult_income",
        url=ADULT_URL,
        csv_name=ADULT_CSV,
        archive_name=ADULT_ARCHIVE,
        raw_members=(ADULT_DATA, "adult.test"),
        citation=(
            "Becker, B., & Kohavi, R. (1996). Adult [Dataset]. UCI Machine "
            "Learning Repository."
        ),
        license="CC BY 4.0",
        doi="10.24432/C5XW20",
    ),
}


class DatasetUnavailable(RuntimeError):
    """Raised when a dataset is neither cached nor downloadable."""


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response:
        with temporary.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    temporary.replace(destination)


def _extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)


def _manual_instructions(info: DatasetInfo, archive: Path, extracted: Path) -> str:
    members = ", ".join(f"data/real/raw/{member}" for member in info.raw_members)
    return (
        f"Dataset {info.name!r} is not cached and could not be downloaded.\n"
        f"  Download: {info.url}\n"
        f"  Save the archive to: {archive}\n"
        f"  Extract it so these files exist: {members}\n"
        f"  (extraction root: {extracted})\n"
        f"Then rerun the command. No substitute data is generated."
    )


def ensure_raw(name: str) -> Path:
    """Ensure the extracted raw files exist, downloading if necessary."""

    info = DATASETS[name]
    extracted = RAW_DIR / name
    missing = [m for m in info.raw_members if not (extracted / m).exists()]
    if not missing:
        return extracted

    archive = RAW_DIR / info.archive_name
    if not archive.exists():
        try:
            _download(info.url, archive)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise DatasetUnavailable(
                f"{_manual_instructions(info, archive, extracted)}\n"
                f"Download error: {type(exc).__name__}: {exc}"
            ) from exc
    try:
        _extract(archive, extracted)
    except zipfile.BadZipFile as exc:
        raise DatasetUnavailable(
            f"The archive {archive} is not a valid zip. Delete it and rerun.\n"
            f"Source: {info.url}"
        ) from exc

    still_missing = [m for m in info.raw_members if not (extracted / m).exists()]
    if still_missing:
        raise DatasetUnavailable(
            f"Archive {archive} did not contain {still_missing}. "
            f"Expected layout is documented in targets/real/README.md."
        )
    return extracted


def _credit_frame(raw: Path) -> pd.DataFrame:
    frame = pd.read_excel(raw / CREDIT_XLS, header=1)
    renamed = {
        "ID": "id",
        "LIMIT_BAL": "limit_bal",
        "SEX": "sex",
        "EDUCATION": "education",
        "MARRIAGE": "marriage",
        "AGE": "age",
        "default payment next month": "target",
    }
    for column in frame.columns:
        if column.startswith(("PAY_", "BILL_AMT", "PAY_AMT")):
            renamed[column] = column.lower()
    frame = frame.rename(columns=renamed)
    frame = frame.drop(columns=["id"])
    # UCI documents 0, 5 and 6 as unknown education codes; collapse to "other".
    frame["education"] = frame["education"].where(
        frame["education"].isin([1, 2, 3, 4]), 4
    )
    frame["marriage"] = frame["marriage"].where(frame["marriage"].isin([1, 2, 3]), 3)
    return frame


def _adult_frame(raw: Path) -> pd.DataFrame:
    columns = [
        "age",
        "workclass",
        "fnlwgt",
        "education",
        "education_num",
        "marital_status",
        "occupation",
        "relationship",
        "race",
        "sex",
        "capital_gain",
        "capital_loss",
        "hours_per_week",
        "native_country",
        "target",
    ]
    frame = pd.read_csv(
        raw / ADULT_DATA, header=None, names=columns, skipinitialspace=True
    )
    for column in frame.select_dtypes(include="object").columns:
        frame[column] = frame[column].astype(str).str.strip()
    # adult.data uses "?" for missing values. Keep the row but mark the value.
    for column in ("workclass", "occupation", "native_country"):
        frame[column] = frame[column].replace("?", "Unknown")
    frame["target"] = (frame["target"] == ">50K").astype(int)
    return frame


def _build_cache(name: str, raw: Path) -> pd.DataFrame:
    if name == "uci_credit_default":
        frame = _credit_frame(raw)
    elif name == "adult_income":
        frame = _adult_frame(raw)
    else:
        raise KeyError(f"unknown dataset: {name}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(DATA_DIR / DATASETS[name].csv_name, index=False)
    return frame


def load_dataset(name: str) -> pd.DataFrame:
    """Return the canonicalised frame, using the committed CSV when present."""

    if name not in DATASETS:
        raise KeyError(f"unknown dataset: {name}")
    info = DATASETS[name]
    csv_path = DATA_DIR / info.csv_name
    if csv_path.exists():
        return pd.read_csv(csv_path)
    raw = ensure_raw(name)
    return _build_cache(name, raw)


def dataset_sha256(name: str) -> str:
    csv_path = DATA_DIR / DATASETS[name].csv_name
    if not csv_path.exists():
        load_dataset(name)
    return hashlib.sha256(csv_path.read_bytes()).hexdigest()


def dataset_summary(name: str) -> dict[str, Any]:
    frame = load_dataset(name)
    info = DATASETS[name]
    return {
        "name": name,
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "positive_rate": float(frame["target"].mean()),
        "citation": info.citation,
        "license": info.license,
        "doi": info.doi,
        "url": info.url,
        "sha256": dataset_sha256(name),
        "cache": (DATA_DIR / info.csv_name).relative_to(REPO_ROOT).as_posix(),
    }

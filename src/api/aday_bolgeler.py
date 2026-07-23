from __future__ import annotations

import json
import sqlite3

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query


# ==========================================================
# PROJE VE VERİTABANI YOLU
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

VERITABANI_YOLU = (
    PROJE_KOKU
    / "data"
    / "database"
    / "urbanai.db"
)


# ==========================================================
# FASTAPI ROUTER
# ==========================================================

router = APIRouter(
    prefix="/api/aday-bolgeler",
    tags=["Aday Bölgeler"],
)


# ==========================================================
# VERİTABANI BAĞLANTISI
# ==========================================================

def veritabanina_baglan() -> sqlite3.Connection:
    """
    UrbanAI SQLite veritabanına bağlanır.
    """

    if not VERITABANI_YOLU.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "UrbanAI veritabanı bulunamadı. "
                "Önce veritabanı hazırlama kodlarını çalıştır."
            ),
        )

    baglanti = sqlite3.connect(
        VERITABANI_YOLU
    )

    baglanti.row_factory = sqlite3.Row

    return baglanti


# ==========================================================
# TABLO KONTROLÜ
# ==========================================================

def aday_bolge_tablosunu_kontrol_et(
    baglanti: sqlite3.Connection,
) -> None:
    """
    candidate_areas tablosunun veritabanında
    bulunup bulunmadığını kontrol eder.
    """

    sonuc = baglanti.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'candidate_areas';
        """
    ).fetchone()

    if sonuc is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "candidate_areas tablosu bulunamadı. "
                "Önce aday bölgeleri veritabanına aktar."
            ),
        )


# ==========================================================
# SQLITE KAYDINI SÖZLÜĞE ÇEVİRME
# ==========================================================

def kaydi_sozluge_cevir(
    kayit: sqlite3.Row,
    geometriyi_ekle: bool = True,
) -> dict[str, Any]:
    """
    SQLite kaydını API'nin döndürebileceği
    Python sözlüğüne dönüştürür.
    """

    sonuc = {
        "id": kayit["id"],
        "hucre_id": kayit["cell_id"],
        "ilce": kayit["district_name"],

        "analiz_yili": kayit["analysis_year"],
        "worldcover_yili": kayit["worldcover_year"],

        "hizmet_ihtiyaci": {
            "sira": kayit["service_need_rank"],
            "puan": kayit["service_need_score"],
            "seviye": kayit["service_need_level"],
        },

        "en_yakin_kutuphane": {
            "ad": kayit["nearest_library_name"],
            "uzaklik_km": (
                kayit["nearest_library_distance_km"]
            ),
        },

        "arazi_ortusu": {
            "yapilasmis_alan_yuzde": (
                kayit["built_up_pct"]
            ),

            "bitkisel_yesil_alan_yuzde": (
                kayit["vegetation_pct"]
            ),

            "acik_ciplak_alan_yuzde": (
                kayit["open_bare_pct"]
            ),

            "su_sulak_alan_yuzde": (
                kayit["water_wetland_pct"]
            ),

            "worldcover_kapsama_yuzde": (
                kayit["worldcover_coverage_pct"]
            ),
        },

        "yer_inceleme": {
            "durum": kayit["site_review_status"],
            "aciklama": (
                kayit["site_review_explanation"]
            ),
        },

        "genel_degerlendirme": (
            kayit["evaluation_text"]
        ),

        "merkez": {
            "enlem": kayit["center_latitude"],
            "boylam": kayit["center_longitude"],
        },

        "guncellenme_zamani_utc": (
            kayit["updated_at_utc"]
        ),
    }

    if geometriyi_ekle:
        geometri_metni = kayit[
            "geometry_geojson"
        ]

        try:
            geometri = json.loads(
                geometri_metni
            )

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            geometri = None

        sonuc["geometri"] = geometri

    return sonuc


# ==========================================================
# ADAY BÖLGELERİ LİSTELEME
# ==========================================================

@router.get("")
def aday_bolgeleri_listele(
    ilce: str | None = Query(
        default=None,
        description=(
            "İlçe adına göre filtreleme. "
            "Örnek: Esenyurt"
        ),
    ),

    analiz_yili: int | None = Query(
        default=None,
        ge=2000,
        le=2100,
        description="Hizmet ihtiyacı analiz yılı.",
    ),

    worldcover_yili: int | None = Query(
        default=None,
        description="WorldCover veri yılı.",
    ),

    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Döndürülecek en fazla kayıt.",
    ),

    geometri: bool = Query(
        default=False,
        description=(
            "True olduğunda hücre geometrisi de döner."
        ),
    ),
) -> dict[str, Any]:
    """
    Aday bölgeleri hizmet ihtiyacı sırasına göre listeler.

    İlçe ve yıl parametreleriyle filtrelenebilir.
    """

    kosullar: list[str] = []
    parametreler: list[Any] = []

    if ilce is not None:
        ilce = ilce.strip()

        if ilce:
            kosullar.append(
                "LOWER(district_name) = LOWER(?)"
            )

            parametreler.append(
                ilce
            )

    if analiz_yili is not None:
        kosullar.append(
            "analysis_year = ?"
        )

        parametreler.append(
            analiz_yili
        )

    if worldcover_yili is not None:
        kosullar.append(
            "worldcover_year = ?"
        )

        parametreler.append(
            worldcover_yili
        )

    where_bolumu = ""

    if kosullar:
        where_bolumu = (
            "WHERE "
            + " AND ".join(
                kosullar
            )
        )

    sorgu = f"""
        SELECT
            *
        FROM candidate_areas
        {where_bolumu}
        ORDER BY
            service_need_score DESC,
            service_need_rank ASC,
            cell_id ASC
        LIMIT ?;
    """

    parametreler.append(
        limit
    )

    with veritabanina_baglan() as baglanti:
        aday_bolge_tablosunu_kontrol_et(
            baglanti
        )

        kayitlar = baglanti.execute(
            sorgu,
            parametreler,
        ).fetchall()

    adaylar = [
        kaydi_sozluge_cevir(
            kayit,
            geometriyi_ekle=geometri,
        )
        for kayit in kayitlar
    ]

    return {
        "filtreler": {
            "ilce": ilce,
            "analiz_yili": analiz_yili,
            "worldcover_yili": worldcover_yili,
            "limit": limit,
            "geometri": geometri,
        },

        "toplam_kayit": len(
            adaylar
        ),

        "aday_bolgeler": adaylar,
    }


# ==========================================================
# TEK ADAY BÖLGE DETAYI
# ==========================================================

@router.get("/{hucre_id}")
def aday_bolge_detayi(
    hucre_id: str,

    ilce: str | None = Query(
        default=None,
        description=(
            "Aynı hücre kimliği farklı ilçelerde "
            "bulunuyorsa ilçe filtresi."
        ),
    ),

    analiz_yili: int | None = Query(
        default=None,
        ge=2000,
        le=2100,
    ),

    worldcover_yili: int | None = Query(
        default=None,
    ),
) -> dict[str, Any]:
    """
    Belirtilen hücre kimliğine ait aday bölgenin
    bütün değerlendirme bilgilerini döndürür.
    """

    hucre_id = hucre_id.strip()

    if not hucre_id:
        raise HTTPException(
            status_code=400,
            detail="Hücre kimliği boş bırakılamaz.",
        )

    kosullar = [
        "cell_id = ?"
    ]

    parametreler: list[Any] = [
        hucre_id
    ]

    if ilce is not None:
        ilce = ilce.strip()

        if ilce:
            kosullar.append(
                "LOWER(district_name) = LOWER(?)"
            )

            parametreler.append(
                ilce
            )

    if analiz_yili is not None:
        kosullar.append(
            "analysis_year = ?"
        )

        parametreler.append(
            analiz_yili
        )

    if worldcover_yili is not None:
        kosullar.append(
            "worldcover_year = ?"
        )

        parametreler.append(
            worldcover_yili
        )

    sorgu = f"""
        SELECT
            *
        FROM candidate_areas
        WHERE {" AND ".join(kosullar)}
        ORDER BY
            analysis_year DESC,
            worldcover_year DESC
        LIMIT 1;
    """

    with veritabanina_baglan() as baglanti:
        aday_bolge_tablosunu_kontrol_et(
            baglanti
        )

        kayit = baglanti.execute(
            sorgu,
            parametreler,
        ).fetchone()

    if kayit is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"{hucre_id} kimlikli aday bölge "
                "bulunamadı."
            ),
        )

    return kaydi_sozluge_cevir(
        kayit,
        geometriyi_ekle=True,
    )
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata

from datetime import datetime, timezone
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

from folium.features import GeoJsonPopup, GeoJsonTooltip
from shapely import union_all
from shapely.geometry import box, shape


# ==========================================================
# PROJE YOLLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

HUCRE_GEOJSON_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "hizmet_boslugu_hucreleri.geojson"
)

ADAY_SIRALAMA_CSV_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "aday_hucre_on_siralama.csv"
)

VERITABANI_YOLU = (
    PROJE_KOKU
    / "data"
    / "database"
    / "urbanai.db"
)


# ==========================================================
# KOORDİNAT SİSTEMLERİ
# ==========================================================

COGRAFI_CRS = "EPSG:4326"

METRIK_CRS = "EPSG:32635"


# ==========================================================
# TÜRKÇE KARAKTER DÖNÜŞÜMÜ
# ==========================================================

TURKCE_KARAKTER_TABLOSU = str.maketrans(
    {
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ı": "i",
        "İ": "i",
        "ö": "o",
        "Ö": "o",
        "ş": "s",
        "Ş": "s",
        "ü": "u",
        "Ü": "u",
    }
)


# ==========================================================
# KOMUT SATIRI ARGÜMANLARI
# ==========================================================

def argumanlari_oku() -> argparse.Namespace:
    """
    İlçe, aday sayısı ve uydu yaması büyüklüğünü
    komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Seçilen ilçe için uydu görüntüsü "
            "pilot analiz alanlarını hazırlar."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "Analiz edilecek ilçe adı. "
            "Örnek: Esenyurt"
        ),
    )

    parser.add_argument(
        "--aday-sayisi",
        type=int,
        default=5,
        help=(
            "İlçeden seçilecek aday hücre sayısı. "
            "Varsayılan: 5"
        ),
    )

    parser.add_argument(
        "--yama-boyutu",
        type=int,
        default=1500,
        help=(
            "Her uydu yamasının metre cinsinden "
            "kenar uzunluğu. Varsayılan: 1500"
        ),
    )

    argumanlar = parser.parse_args()

    argumanlar.ilce = argumanlar.ilce.strip()

    if not argumanlar.ilce:
        parser.error(
            "--ilce değeri boş bırakılamaz."
        )

    if argumanlar.aday_sayisi <= 0:
        parser.error(
            "--aday-sayisi sıfırdan büyük olmalıdır."
        )

    if argumanlar.yama_boyutu <= 0:
        parser.error(
            "--yama-boyutu sıfırdan büyük olmalıdır."
        )

    return argumanlar


# ==========================================================
# GÜVENLİ DOSYA VE KLASÖR ADI
# ==========================================================

def slug_olustur(
    metin: str,
) -> str:
    """
    İlçe adını dosya ve klasörlerde kullanılabilecek
    güvenli bir metne dönüştürür.

    Örnekler:
    Küçükçekmece -> kucukcekmece
    Bağcılar     -> bagcilar
    Ümraniye     -> umraniye
    """

    temiz_metin = (
        metin
        .translate(
            TURKCE_KARAKTER_TABLOSU
        )
        .lower()
        .strip()
    )

    temiz_metin = unicodedata.normalize(
        "NFKD",
        temiz_metin,
    )

    temiz_metin = "".join(
        karakter
        for karakter in temiz_metin
        if not unicodedata.combining(
            karakter
        )
    )

    temiz_metin = re.sub(
        r"[^a-z0-9]+",
        "_",
        temiz_metin,
    )

    temiz_metin = temiz_metin.strip(
        "_"
    )

    if not temiz_metin:
        raise ValueError(
            "İlçe adından güvenli klasör adı oluşturulamadı."
        )

    return temiz_metin


# ==========================================================
# ÇIKTI YOLLARI
# ==========================================================

def cikti_yollarini_olustur(
    ilce_slug: str,
) -> dict[str, Path]:
    """
    İlçeye özel işlenmiş veri ve frontend
    çıktı yollarını oluşturur.
    """

    islenmis_klasor = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    return {
        "islenmis_klasor": islenmis_klasor,

        "pilot_aday_geojson": (
            islenmis_klasor
            / "pilot_aday_hucreleri.geojson"
        ),

        "uydu_yamalari_geojson": (
            islenmis_klasor
            / "pilot_uydu_yamalari.geojson"
        ),

        "uydu_bbox_csv": (
            islenmis_klasor
            / "pilot_uydu_bbox.csv"
        ),

        "birlesik_alan_geojson": (
            islenmis_klasor
            / "pilot_birlesik_alan.geojson"
        ),

        "ayarlar_json": (
            islenmis_klasor
            / "pilot_ayarlar.json"
        ),

        "harita_html": (
            PROJE_KOKU
            / "frontend"
            / f"{ilce_slug}_pilot_uydu_alanlari.html"
        ),
    }


# ==========================================================
# GİRDİ DOSYALARINI KONTROL ETME
# ==========================================================

def girdi_dosyalarini_kontrol_et() -> None:
    """
    Analiz için gereken temel dosyaların
    var olup olmadığını kontrol eder.
    """

    eksik_dosyalar = []

    if not HUCRE_GEOJSON_YOLU.exists():
        eksik_dosyalar.append(
            HUCRE_GEOJSON_YOLU
        )

    if not ADAY_SIRALAMA_CSV_YOLU.exists():
        eksik_dosyalar.append(
            ADAY_SIRALAMA_CSV_YOLU
        )

    if eksik_dosyalar:
        hata_metni = "\n".join(
            str(dosya)
            for dosya in eksik_dosyalar
        )

        raise FileNotFoundError(
            "Gerekli analiz dosyaları bulunamadı:\n"
            f"{hata_metni}\n\n"
            "Önce hizmet boşluğu ve aday hücre "
            "sıralama analizlerini çalıştır."
        )


# ==========================================================
# HÜCRE VE ADAY VERİLERİNİ OKUMA
# ==========================================================

def verileri_oku(
    ilce_adi: str,
    aday_sayisi: int,
) -> tuple[
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
]:
    """
    Seçilen ilçenin ilk N aday hücresini ve
    ilçedeki bütün analiz hücrelerini okur.
    """

    girdi_dosyalarini_kontrol_et()

    hedef_slug = slug_olustur(
        ilce_adi
    )

    tum_hucreler = gpd.read_file(
        HUCRE_GEOJSON_YOLU
    )

    aday_siralamasi = pd.read_csv(
        ADAY_SIRALAMA_CSV_YOLU
    )

    gerekli_hucre_sutunlari = [
        "cell_id",
        "district_name",
        "center_latitude",
        "center_longitude",
        "nearest_library_name",
        "nearest_library_distance_km",
        "geometry",
    ]

    gerekli_aday_sutunlari = [
        "cell_id",
        "district_name",
        "global_candidate_rank",
        "district_candidate_rank",
        "global_preliminary_score",
        "preliminary_need_score",
    ]

    eksik_hucre_sutunlari = [
        sutun
        for sutun in gerekli_hucre_sutunlari
        if sutun not in tum_hucreler.columns
    ]

    eksik_aday_sutunlari = [
        sutun
        for sutun in gerekli_aday_sutunlari
        if sutun not in aday_siralamasi.columns
    ]

    if eksik_hucre_sutunlari:
        raise ValueError(
            "Hücre GeoJSON dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_hucre_sutunlari
            )
        )

    if eksik_aday_sutunlari:
        raise ValueError(
            "Aday sıralama CSV dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_aday_sutunlari
            )
        )

    if tum_hucreler.crs is None:
        tum_hucreler = tum_hucreler.set_crs(
            COGRAFI_CRS
        )

    tum_hucreler[
        "cell_id"
    ] = (
        tum_hucreler[
            "cell_id"
        ]
        .astype(str)
    )

    aday_siralamasi[
        "cell_id"
    ] = (
        aday_siralamasi[
            "cell_id"
        ]
        .astype(str)
    )

    tum_hucreler[
        "_district_slug"
    ] = (
        tum_hucreler[
            "district_name"
        ]
        .astype(str)
        .map(
            slug_olustur
        )
    )

    aday_siralamasi[
        "_district_slug"
    ] = (
        aday_siralamasi[
            "district_name"
        ]
        .astype(str)
        .map(
            slug_olustur
        )
    )

    aday_siralamasi[
        "district_candidate_rank"
    ] = pd.to_numeric(
        aday_siralamasi[
            "district_candidate_rank"
        ],
        errors="coerce",
    )

    ilce_adaylari = aday_siralamasi[
        aday_siralamasi[
            "_district_slug"
        ]
        == hedef_slug
    ].copy()

    if ilce_adaylari.empty:
        mevcut_ilceler = sorted(
            aday_siralamasi[
                "district_name"
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        raise ValueError(
            f"{ilce_adi} için aday hücre bulunamadı.\n\n"
            "Aday verisi bulunan ilçeler:\n"
            + ", ".join(
                mevcut_ilceler
            )
        )

    ilce_adaylari = (
        ilce_adaylari
        .sort_values(
            by="district_candidate_rank",
            ascending=True,
        )
        .head(
            aday_sayisi
        )
        .copy()
    )

    gercek_aday_sayisi = len(
        ilce_adaylari
    )

    if gercek_aday_sayisi < aday_sayisi:
        print(
            f"Uyarı: {ilce_adi} için "
            f"{aday_sayisi} yerine "
            f"{gercek_aday_sayisi} aday bulundu."
        )

    siralama_sutunlari = [
        "cell_id",
        "global_candidate_rank",
        "district_candidate_rank",
        "global_distance_score",
        "district_distance_score",
        "global_preliminary_score",
        "preliminary_need_score",
    ]

    mevcut_siralama_sutunlari = [
        sutun
        for sutun in siralama_sutunlari
        if sutun in ilce_adaylari.columns
    ]

    pilot_aday_hucreleri = (
        tum_hucreler
        .merge(
            ilce_adaylari[
                mevcut_siralama_sutunlari
            ],
            on="cell_id",
            how="inner",
        )
    )

    pilot_aday_hucreleri = gpd.GeoDataFrame(
        pilot_aday_hucreleri,
        geometry="geometry",
        crs=tum_hucreler.crs,
    )

    pilot_aday_hucreleri[
        "district_candidate_rank"
    ] = pd.to_numeric(
        pilot_aday_hucreleri[
            "district_candidate_rank"
        ],
        errors="raise",
    ).astype(int)

    pilot_aday_hucreleri = (
        pilot_aday_hucreleri
        .sort_values(
            by="district_candidate_rank",
            ascending=True,
        )
        .reset_index(
            drop=True
        )
    )

    ilce_tum_hucreleri = (
        tum_hucreler[
            tum_hucreler[
                "_district_slug"
            ]
            == hedef_slug
        ]
        .copy()
    )

    ilce_tum_hucreleri = gpd.GeoDataFrame(
        ilce_tum_hucreleri,
        geometry="geometry",
        crs=tum_hucreler.crs,
    )

    pilot_aday_hucreleri = (
        pilot_aday_hucreleri
        .drop(
            columns=[
                "_district_slug",
            ],
            errors="ignore",
        )
    )

    ilce_tum_hucreleri = (
        ilce_tum_hucreleri
        .drop(
            columns=[
                "_district_slug",
            ],
            errors="ignore",
        )
    )

    return (
        pilot_aday_hucreleri,
        ilce_tum_hucreleri,
    )


# ==========================================================
# UYDU YAMALARINI OLUŞTURMA
# ==========================================================

def uydu_yamalarini_olustur(
    pilot_aday_hucreleri: gpd.GeoDataFrame,
    ilce_adi: str,
    ilce_slug: str,
    yama_boyutu_metre: int,
) -> gpd.GeoDataFrame:
    """
    Her aday hücrenin merkezinde kare biçimli
    uydu görüntüsü sorgu alanı oluşturur.
    """

    adaylar_metrik = (
        pilot_aday_hucreleri
        .to_crs(
            METRIK_CRS
        )
    )

    yarim_yama = (
        yama_boyutu_metre
        / 2
    )

    yama_kayitlari = []

    for aday in adaylar_metrik.itertuples():

        merkez_noktasi = (
            aday.geometry
            .representative_point()
        )

        uydu_yamasi = box(
            merkez_noktasi.x - yarim_yama,
            merkez_noktasi.y - yarim_yama,
            merkez_noktasi.x + yarim_yama,
            merkez_noktasi.y + yarim_yama,
        )

        yama_kayitlari.append(
            {
                "patch_id": (
                    f"{ilce_slug.upper()}_"
                    f"{int(aday.district_candidate_rank):02d}"
                ),
                "cell_id": str(
                    aday.cell_id
                ),
                "district_name": ilce_adi,
                "district_slug": ilce_slug,
                "district_candidate_rank": int(
                    aday.district_candidate_rank
                ),
                "global_candidate_rank": int(
                    aday.global_candidate_rank
                ),
                "nearest_library_name": (
                    aday.nearest_library_name
                ),
                "nearest_library_distance_km": float(
                    aday.nearest_library_distance_km
                ),
                "global_preliminary_score": float(
                    aday.global_preliminary_score
                ),
                "preliminary_need_score": float(
                    aday.preliminary_need_score
                ),
                "patch_width_m": (
                    yama_boyutu_metre
                ),
                "patch_height_m": (
                    yama_boyutu_metre
                ),
                "geometry": uydu_yamasi,
            }
        )

    uydu_yamalari = gpd.GeoDataFrame(
        yama_kayitlari,
        geometry="geometry",
        crs=METRIK_CRS,
    )

    return uydu_yamalari.to_crs(
        COGRAFI_CRS
    )


# ==========================================================
# BBOX BİLGİLERİNİ EKLEME
# ==========================================================

def bbox_bilgilerini_ekle(
    uydu_yamalari: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Uydu veri servisinde kullanılacak sınır
    koordinatlarını hesaplar.
    """

    sonuc = uydu_yamalari.copy()

    sinirlar = sonuc.geometry.bounds

    sonuc[
        "min_longitude"
    ] = sinirlar[
        "minx"
    ].round(7)

    sonuc[
        "min_latitude"
    ] = sinirlar[
        "miny"
    ].round(7)

    sonuc[
        "max_longitude"
    ] = sinirlar[
        "maxx"
    ].round(7)

    sonuc[
        "max_latitude"
    ] = sinirlar[
        "maxy"
    ].round(7)

    return gpd.GeoDataFrame(
        sonuc,
        geometry="geometry",
        crs=uydu_yamalari.crs,
    )


# ==========================================================
# İLÇE SINIRINI VERİTABANINDAN OKUMA
# ==========================================================

def ilce_sinirini_veritabanindan_oku(
    ilce_adi: str,
) -> gpd.GeoDataFrame | None:
    """
    İlçenin gerçek sınır geometrisini SQLite
    veritabanından okumayı dener.
    """

    if not VERITABANI_YOLU.exists():
        return None

    hedef_slug = slug_olustur(
        ilce_adi
    )

    try:
        with sqlite3.connect(
            VERITABANI_YOLU
        ) as baglanti:

            kayitlar = baglanti.execute(
                """
                SELECT
                    name,
                    geometry_geojson
                FROM districts
                WHERE geometry_geojson IS NOT NULL
                """
            ).fetchall()

    except sqlite3.Error:
        return None

    for ilce_ismi, geometri_metni in kayitlar:

        if slug_olustur(
            str(
                ilce_ismi
            )
        ) != hedef_slug:
            continue

        try:
            geometri = shape(
                json.loads(
                    geometri_metni
                )
            )

        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            return None

        return gpd.GeoDataFrame(
            [
                {
                    "district_name": (
                        ilce_ismi
                    ),
                    "geometry": geometri,
                }
            ],
            geometry="geometry",
            crs=COGRAFI_CRS,
        )

    return None


# ==========================================================
# İLÇE SINIRINI OLUŞTURMA
# ==========================================================

def ilce_sinirini_olustur(
    ilce_adi: str,
    ilce_tum_hucreleri: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Öncelikle veritabanındaki gerçek ilçe sınırını kullanır.

    Veritabanında geometri bulunamazsa analiz hücrelerini
    birleştirerek yaklaşık sınır oluşturur.
    """

    veritabani_siniri = (
        ilce_sinirini_veritabanindan_oku(
            ilce_adi
        )
    )

    if veritabani_siniri is not None:
        return veritabani_siniri

    birlesik_geometri = union_all(
        list(
            ilce_tum_hucreleri.geometry
        )
    )

    return gpd.GeoDataFrame(
        [
            {
                "district_name": ilce_adi,
                "geometry_source": (
                    "Analiz hücrelerinin birleşimi"
                ),
                "geometry": birlesik_geometri,
            }
        ],
        geometry="geometry",
        crs=ilce_tum_hucreleri.crs,
    )


# ==========================================================
# BİRLEŞİK PİLOT ALANI
# ==========================================================

def birlesik_pilot_alani_olustur(
    uydu_yamalari: gpd.GeoDataFrame,
    ilce_adi: str,
    ilce_slug: str,
    yama_boyutu_metre: int,
) -> gpd.GeoDataFrame:
    """
    Bütün uydu yamalarını tek bir coğrafi
    geometri altında birleştirir.
    """

    birlesik_geometri = union_all(
        list(
            uydu_yamalari.geometry
        )
    )

    return gpd.GeoDataFrame(
        [
            {
                "district_name": ilce_adi,
                "district_slug": ilce_slug,
                "patch_count": len(
                    uydu_yamalari
                ),
                "patch_size_m": (
                    yama_boyutu_metre
                ),
                "geometry": birlesik_geometri,
            }
        ],
        geometry="geometry",
        crs=uydu_yamalari.crs,
    )


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    pilot_aday_hucreleri: gpd.GeoDataFrame,
    uydu_yamalari: gpd.GeoDataFrame,
    birlesik_pilot_alani: gpd.GeoDataFrame,
    ilce_adi: str,
    ilce_slug: str,
    aday_sayisi: int,
    yama_boyutu_metre: int,
    yollar: dict[str, Path],
) -> None:
    """
    İlçeye ait analiz sonuçlarını kendi klasörüne kaydeder.
    """

    yollar[
        "islenmis_klasor"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    yollar[
        "pilot_aday_geojson"
    ].write_text(
        pilot_aday_hucreleri.to_json(
            ensure_ascii=False
        ),
        encoding="utf-8",
    )

    yollar[
        "uydu_yamalari_geojson"
    ].write_text(
        uydu_yamalari.to_json(
            ensure_ascii=False
        ),
        encoding="utf-8",
    )

    yollar[
        "birlesik_alan_geojson"
    ].write_text(
        birlesik_pilot_alani.to_json(
            ensure_ascii=False
        ),
        encoding="utf-8",
    )

    bbox_sutunlari = [
        "patch_id",
        "cell_id",
        "district_name",
        "district_slug",
        "district_candidate_rank",
        "global_candidate_rank",
        "nearest_library_name",
        "nearest_library_distance_km",
        "global_preliminary_score",
        "preliminary_need_score",
        "patch_width_m",
        "patch_height_m",
        "min_longitude",
        "min_latitude",
        "max_longitude",
        "max_latitude",
    ]

    uydu_yamalari[
        bbox_sutunlari
    ].to_csv(
        yollar[
            "uydu_bbox_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    ayarlar = {
        "project": (
            "UrbanAI 3D İstanbul"
        ),
        "district_name": ilce_adi,
        "district_slug": ilce_slug,
        "requested_candidate_count": (
            aday_sayisi
        ),
        "created_candidate_count": len(
            pilot_aday_hucreleri
        ),
        "patch_size_m": (
            yama_boyutu_metre
        ),
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "source_candidate_file": str(
            ADAY_SIRALAMA_CSV_YOLU
        ),
        "source_cell_file": str(
            HUCRE_GEOJSON_YOLU
        ),
    }

    yollar[
        "ayarlar_json"
    ].write_text(
        json.dumps(
            ayarlar,
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )


# ==========================================================
# HARİTA BİLGİ PANELİ
# ==========================================================

def bilgi_paneli_ekle(
    harita: folium.Map,
    ilce_adi: str,
    aday_sayisi: int,
    yama_boyutu_metre: int,
) -> None:
    """
    Haritaya dinamik analiz açıklaması ekler.
    """

    panel_html = f"""
    <div style="
        position: fixed;
        top: 18px;
        left: 55px;
        z-index: 9999;
        width: 385px;
        padding: 17px 19px;
        border-radius: 13px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.17);
        font-family: Arial, sans-serif;
        color: #172033;
    ">
        <div style="
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 8px;
        ">
            {ilce_adi} Pilot Uydu Analiz Alanları
        </div>

        <div style="
            font-size: 11px;
            line-height: 1.6;
            color: #5e6878;
        ">
            İlçedeki ilk {aday_sayisi} aday hücrenin
            çevresinde {yama_boyutu_metre} ×
            {yama_boyutu_metre} metrelik uydu
            görüntüsü sorgu alanları hazırlanmıştır.
            İlçe adı ve analiz ayarları komut satırından
            alınmaktadır.
        </div>
    </div>
    """

    harita.get_root().html.add_child(
        folium.Element(
            panel_html
        )
    )


# ==========================================================
# HARİTA OLUŞTURMA
# ==========================================================

def harita_olustur(
    pilot_aday_hucreleri: gpd.GeoDataFrame,
    uydu_yamalari: gpd.GeoDataFrame,
    ilce_siniri: gpd.GeoDataFrame,
    ilce_adi: str,
    yama_boyutu_metre: int,
    harita_yolu: Path,
) -> None:
    """
    Pilot adayları, uydu yamalarını ve ilçe sınırını
    etkileşimli haritada gösterir.
    """

    harita_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    pilot_aday_hucreleri = (
        pilot_aday_hucreleri
        .to_crs(
            COGRAFI_CRS
        )
    )

    uydu_yamalari = (
        uydu_yamalari
        .to_crs(
            COGRAFI_CRS
        )
    )

    ilce_siniri = (
        ilce_siniri
        .to_crs(
            COGRAFI_CRS
        )
    )

    merkez_noktasi = (
        uydu_yamalari
        .to_crs(
            METRIK_CRS
        )
        .geometry
        .union_all()
        .centroid
    )

    merkez_cografi = (
        gpd.GeoSeries(
            [
                merkez_noktasi
            ],
            crs=METRIK_CRS,
        )
        .to_crs(
            COGRAFI_CRS
        )
        .iloc[0]
    )

    harita = folium.Map(
        location=[
            merkez_cografi.y,
            merkez_cografi.x,
        ],
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=True,
    )

    folium.GeoJson(
        data=ilce_siniri.to_json(
            ensure_ascii=False
        ),
        name=f"{ilce_adi} ilçe sınırı",
        style_function=lambda feature: {
            "fillColor": "transparent",
            "color": "#111827",
            "weight": 3,
            "fillOpacity": 0,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "district_name",
            ],
            aliases=[
                "İlçe:",
            ],
            sticky=True,
        ),
    ).add_to(
        harita
    )

    folium.GeoJson(
        data=pilot_aday_hucreleri.to_json(
            ensure_ascii=False
        ),
        name="Seçilen aday hücreler",
        style_function=lambda feature: {
            "fillColor": "#dc2626",
            "color": "#7f1d1d",
            "weight": 2,
            "fillOpacity": 0.62,
        },
        highlight_function=lambda feature: {
            "color": "#000000",
            "weight": 3,
            "fillOpacity": 0.85,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "district_name",
                "district_candidate_rank",
                "nearest_library_distance_km",
            ],
            aliases=[
                "İlçe:",
                "Aday sırası:",
                "Kütüphaneye uzaklık (km):",
            ],
            localize=True,
            sticky=True,
        ),
        popup=GeoJsonPopup(
            fields=[
                "cell_id",
                "district_candidate_rank",
                "global_candidate_rank",
                "nearest_library_name",
                "nearest_library_distance_km",
                "global_preliminary_score",
                "preliminary_need_score",
            ],
            aliases=[
                "Hücre:",
                "İlçe içi sıra:",
                "Genel sıra:",
                "En yakın kütüphane:",
                "Uzaklık (km):",
                "Genel ön eleme puanı:",
                "İlçe içi ön eleme puanı:",
            ],
            labels=True,
            localize=True,
        ),
    ).add_to(
        harita
    )

    folium.GeoJson(
        data=uydu_yamalari.to_json(
            ensure_ascii=False
        ),
        name=f"{yama_boyutu_metre} metrelik uydu yamaları",
        style_function=lambda feature: {
            "fillColor": "#2563eb",
            "color": "#1d4ed8",
            "weight": 2,
            "dashArray": "7, 5",
            "fillOpacity": 0.16,
        },
        highlight_function=lambda feature: {
            "weight": 4,
            "fillOpacity": 0.28,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "patch_id",
                "district_candidate_rank",
            ],
            aliases=[
                "Uydu yaması:",
                "Aday sırası:",
            ],
            sticky=True,
        ),
        popup=GeoJsonPopup(
            fields=[
                "patch_id",
                "cell_id",
                "district_candidate_rank",
                "nearest_library_distance_km",
                "patch_width_m",
                "patch_height_m",
                "min_longitude",
                "min_latitude",
                "max_longitude",
                "max_latitude",
            ],
            aliases=[
                "Yama kimliği:",
                "Hücre kimliği:",
                "Aday sırası:",
                "Kütüphaneye uzaklık (km):",
                "Yama genişliği (m):",
                "Yama yüksekliği (m):",
                "Minimum boylam:",
                "Minimum enlem:",
                "Maksimum boylam:",
                "Maksimum enlem:",
            ],
            labels=True,
            localize=True,
        ),
    ).add_to(
        harita
    )

    for yama in uydu_yamalari.itertuples():

        merkez = (
            yama.geometry
            .representative_point()
        )

        folium.CircleMarker(
            location=[
                merkez.y,
                merkez.x,
            ],
            radius=6,
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color="#1d4ed8",
            fill_opacity=1,
            tooltip=(
                f"{yama.patch_id} – "
                f"{yama.district_candidate_rank}. aday"
            ),
        ).add_to(
            harita
        )

    toplam_sinir = (
        uydu_yamalari.total_bounds
    )

    harita.fit_bounds(
        [
            [
                toplam_sinir[1],
                toplam_sinir[0],
            ],
            [
                toplam_sinir[3],
                toplam_sinir[2],
            ],
        ]
    )

    bilgi_paneli_ekle(
        harita,
        ilce_adi,
        len(
            pilot_aday_hucreleri
        ),
        yama_boyutu_metre,
    )

    folium.LayerControl(
        collapsed=False
    ).add_to(
        harita
    )

    harita.save(
        harita_yolu
    )


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    ilce_adi: str,
    ilce_slug: str,
    pilot_aday_hucreleri: gpd.GeoDataFrame,
    uydu_yamalari: gpd.GeoDataFrame,
    yama_boyutu_metre: int,
    yollar: dict[str, Path],
) -> None:
    """
    Oluşturulan genel pilot analizi terminalde özetler.
    """

    print()
    print("=" * 95)
    print("PİLOT UYDU ANALİZ ALANLARI HAZIRLANDI")
    print("=" * 95)

    print()
    print(
        "Pilot ilçe:",
        ilce_adi,
    )

    print(
        "Güvenli ilçe adı:",
        ilce_slug,
    )

    print(
        "Seçilen aday hücre sayısı:",
        len(
            pilot_aday_hucreleri
        ),
    )

    print(
        "Oluşturulan uydu yaması sayısı:",
        len(
            uydu_yamalari
        ),
    )

    print(
        "Her uydu yamasının büyüklüğü:",
        f"{yama_boyutu_metre} x "
        f"{yama_boyutu_metre} metre",
    )

    print()
    print(
        "Uydu görüntüsü sorgu alanları:"
    )

    sirali_yamalar = (
        uydu_yamalari
        .sort_values(
            by="district_candidate_rank",
            ascending=True,
        )
    )

    for yama in sirali_yamalar.itertuples():

        print()
        print(
            f"  {yama.patch_id}"
        )

        print(
            f"    Hücre: "
            f"{yama.cell_id}"
        )

        print(
            f"    Aday sırası: "
            f"{int(yama.district_candidate_rank)}"
        )

        print(
            f"    Kütüphaneye uzaklık: "
            f"{yama.nearest_library_distance_km:.2f} km"
        )

        print(
            "    BBOX:"
        )

        print(
            f"      {yama.min_longitude}, "
            f"{yama.min_latitude}, "
            f"{yama.max_longitude}, "
            f"{yama.max_latitude}"
        )

    print()
    print(
        "İlçeye özel işlenmiş veri klasörü:"
    )

    print(
        f"  {yollar['islenmis_klasor']}"
    )

    print()
    print(
        "BBOX tablosu:"
    )

    print(
        f"  {yollar['uydu_bbox_csv']}"
    )

    print()
    print(
        "Analiz ayarları:"
    )

    print(
        f"  {yollar['ayarlar_json']}"
    )

    print()
    print(
        "Etkileşimli pilot haritası:"
    )

    print(
        f"  {yollar['harita_html']}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Seçilen herhangi bir ilçe için pilot uydu
    analiz alanlarını hazırlar.
    """

    argumanlar = argumanlari_oku()

    ilce_adi = argumanlar.ilce

    ilce_slug = slug_olustur(
        ilce_adi
    )

    yollar = cikti_yollarini_olustur(
        ilce_slug
    )

    print()
    print(
        "Analiz ayarları:"
    )

    print(
        f"  İlçe: {ilce_adi}"
    )

    print(
        f"  Aday sayısı: "
        f"{argumanlar.aday_sayisi}"
    )

    print(
        f"  Yama boyutu: "
        f"{argumanlar.yama_boyutu} metre"
    )

    print()
    print(
        "Hizmet boşluğu hücreleri ve aday "
        "sıralaması okunuyor..."
    )

    (
        pilot_aday_hucreleri,
        ilce_tum_hucreleri,
    ) = verileri_oku(
        ilce_adi,
        argumanlar.aday_sayisi,
    )

    print(
        "Uydu görüntüsü sorgu yamaları oluşturuluyor..."
    )

    uydu_yamalari = uydu_yamalarini_olustur(
        pilot_aday_hucreleri,
        ilce_adi,
        ilce_slug,
        argumanlar.yama_boyutu,
    )

    print(
        "Uydu yaması BBOX koordinatları hesaplanıyor..."
    )

    uydu_yamalari = bbox_bilgilerini_ekle(
        uydu_yamalari
    )

    print(
        "İlçe sınırı hazırlanıyor..."
    )

    ilce_siniri = ilce_sinirini_olustur(
        ilce_adi,
        ilce_tum_hucreleri,
    )

    print(
        "Birleşik pilot analiz alanı oluşturuluyor..."
    )

    birlesik_pilot_alani = (
        birlesik_pilot_alani_olustur(
            uydu_yamalari,
            ilce_adi,
            ilce_slug,
            argumanlar.yama_boyutu,
        )
    )

    print(
        "İlçeye özel analiz dosyaları kaydediliyor..."
    )

    ciktilari_kaydet(
        pilot_aday_hucreleri,
        uydu_yamalari,
        birlesik_pilot_alani,
        ilce_adi,
        ilce_slug,
        argumanlar.aday_sayisi,
        argumanlar.yama_boyutu,
        yollar,
    )

    print(
        "Etkileşimli pilot haritası oluşturuluyor..."
    )

    harita_olustur(
        pilot_aday_hucreleri,
        uydu_yamalari,
        ilce_siniri,
        ilce_adi,
        argumanlar.yama_boyutu,
        yollar[
            "harita_html"
        ],
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        ilce_slug,
        pilot_aday_hucreleri,
        uydu_yamalari,
        argumanlar.yama_boyutu,
        yollar,
    )


if __name__ == "__main__":
    main()
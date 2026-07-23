from __future__ import annotations

import argparse
import html
import re
import unicodedata
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

from folium.features import GeoJsonPopup, GeoJsonTooltip
from folium.plugins import Fullscreen, MiniMap


# ==========================================================
# PROJE KÖK KLASÖRÜ
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]


# ==========================================================
# KOORDİNAT SİSTEMLERİ
# ==========================================================

COGRAFI_CRS = "EPSG:4326"
ISTANBUL_METRIK_CRS = "EPSG:32635"


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
    Haritası hazırlanacak ilçe ve WorldCover yılını
    komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Aday hizmet hücrelerini, hizmet ihtiyacı "
            "ve yer inceleme durumlarıyla birlikte "
            "etkileşimli haritada gösterir."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help="Haritası hazırlanacak ilçe adı. Örnek: Esenyurt",
    )

    parser.add_argument(
        "--yil",
        type=int,
        default=2021,
        choices=[2020, 2021],
        help="Kullanılan WorldCover yılı. Varsayılan: 2021",
    )

    argumanlar = parser.parse_args()
    argumanlar.ilce = argumanlar.ilce.strip()

    if not argumanlar.ilce:
        parser.error("--ilce değeri boş bırakılamaz.")

    return argumanlar


# ==========================================================
# GÜVENLİ DOSYA VE KLASÖR ADI
# ==========================================================

def slug_olustur(metin: str) -> str:
    """
    Türkçe ilçe adını güvenli klasör adına dönüştürür.

    Örnekler:
    Küçükçekmece -> kucukcekmece
    Bağcılar     -> bagcilar
    Ümraniye     -> umraniye
    """

    temiz_metin = (
        metin
        .translate(TURKCE_KARAKTER_TABLOSU)
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
        if not unicodedata.combining(karakter)
    )

    temiz_metin = re.sub(
        r"[^a-z0-9]+",
        "_",
        temiz_metin,
    )

    temiz_metin = temiz_metin.strip("_")

    if not temiz_metin:
        raise ValueError(
            "İlçe adından güvenli klasör adı oluşturulamadı."
        )

    return temiz_metin


# ==========================================================
# DOSYA YOLLARI
# ==========================================================

def dosya_yollarini_olustur(
    ilce_slug: str,
) -> dict[str, Path]:
    """
    Haritanın girdi ve çıktı yollarını oluşturur.
    """

    ilce_uydu_klasoru = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    degerlendirme_klasoru = (
        ilce_uydu_klasoru
        / "candidate_evaluation"
    )

    return {
        "aday_hucre_geojson": (
            ilce_uydu_klasoru
            / "pilot_aday_hucreleri.geojson"
        ),

        "degerlendirme_csv": (
            degerlendirme_klasoru
            / "aday_bolge_iki_eksen_degerlendirmesi.csv"
        ),

        "birlesik_geojson": (
            degerlendirme_klasoru
            / "aday_bolge_degerlendirme_haritasi.geojson"
        ),

        "harita_html": (
            PROJE_KOKU
            / "frontend"
            / f"{ilce_slug}_aday_bolge_degerlendirme_haritasi.html"
        ),
    }


# ==========================================================
# ADAY HÜCRE GEOMETRİLERİNİ OKUMA
# ==========================================================

def aday_hucreleri_oku(
    geojson_yolu: Path,
) -> gpd.GeoDataFrame:
    """
    Aday hücrelerin gerçek harita geometrilerini okur.
    """

    if not geojson_yolu.exists():
        raise FileNotFoundError(
            "Pilot aday hücreleri GeoJSON dosyası bulunamadı:\n"
            f"{geojson_yolu}\n\n"
            "Önce pilot_uydu_alanlari_hazirlama.py "
            "dosyasını çalıştır."
        )

    adaylar = gpd.read_file(geojson_yolu)

    gerekli_sutunlar = [
        "cell_id",
        "geometry",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in adaylar.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Aday hücre dosyasında eksik sütunlar var:\n"
            + "\n".join(eksik_sutunlar)
        )

    if adaylar.crs is None:
        raise ValueError(
            "Aday hücre GeoJSON dosyasında "
            "koordinat sistemi bulunamadı."
        )

    adaylar["cell_id"] = (
        adaylar["cell_id"]
        .astype(str)
        .str.strip()
    )

    adaylar = adaylar.dropna(
        subset=[
            "cell_id",
            "geometry",
        ]
    ).copy()

    adaylar = adaylar[
        ~adaylar.geometry.is_empty
    ].copy()

    if adaylar.empty:
        raise ValueError(
            "Haritada gösterilebilecek aday "
            "hücre bulunamadı."
        )

    return gpd.GeoDataFrame(
        adaylar,
        geometry="geometry",
        crs=adaylar.crs,
    )


# ==========================================================
# DEĞERLENDİRME SONUÇLARINI OKUMA
# ==========================================================

def degerlendirme_sonuclarini_oku(
    csv_yolu: Path,
) -> pd.DataFrame:
    """
    İki eksenli aday değerlendirme sonuçlarını okur.
    """

    if not csv_yolu.exists():
        raise FileNotFoundError(
            "İki eksenli aday değerlendirme CSV dosyası "
            "bulunamadı:\n"
            f"{csv_yolu}\n\n"
            "Önce aday_bolge_degerlendirmesi.py "
            "dosyasını çalıştır."
        )

    dataframe = pd.read_csv(csv_yolu)

    gerekli_sutunlar = [
        "cell_id",
        "service_need_rank",
        "service_need_score",
        "service_need_level",
        "nearest_library_name",
        "nearest_library_distance_km",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
        "site_review_status",
        "site_review_explanation",
        "evaluation_text",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in dataframe.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Değerlendirme CSV dosyasında eksik "
            "sütunlar var:\n"
            + "\n".join(eksik_sutunlar)
        )

    dataframe["cell_id"] = (
        dataframe["cell_id"]
        .astype(str)
        .str.strip()
    )

    sayisal_sutunlar = [
        "service_need_rank",
        "service_need_score",
        "nearest_library_distance_km",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
    ]

    for sutun in sayisal_sutunlar:
        dataframe[sutun] = pd.to_numeric(
            dataframe[sutun],
            errors="coerce",
        )

    dataframe = dataframe.dropna(
        subset=[
            "cell_id",
            "service_need_rank",
            "service_need_score",
        ]
    ).copy()

    dataframe["service_need_rank"] = (
        dataframe["service_need_rank"]
        .astype(int)
    )

    if dataframe.empty:
        raise ValueError(
            "Haritaya aktarılabilecek değerlendirme "
            "sonucu bulunamadı."
        )

    return dataframe


# ==========================================================
# GEOMETRİ VE DEĞERLENDİRMEYİ BİRLEŞTİRME
# ==========================================================

def verileri_birlestir(
    adaylar: gpd.GeoDataFrame,
    degerlendirmeler: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """
    Aday hücre geometrileriyle değerlendirme
    sonuçlarını cell_id üzerinden birleştirir.

    GeoJSON dosyasından yalnızca cell_id ve geometry
    alınır. Böylece aynı adlı sütunlarda _x ve _y
    oluşması engellenir.
    """

    aday_geometrileri = adaylar[
        [
            "cell_id",
            "geometry",
        ]
    ].copy()

    aday_geometrileri = gpd.GeoDataFrame(
        aday_geometrileri,
        geometry="geometry",
        crs=adaylar.crs,
    )

    degerlendirme_sutunlari = [
        "cell_id",
        "district_name",
        "service_need_rank",
        "service_need_score",
        "service_need_level",
        "nearest_library_name",
        "nearest_library_distance_km",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
        "urbanization_level",
        "open_area_level",
        "urban_demand_context",
        "site_review_status",
        "site_review_explanation",
        "evaluation_text",
    ]

    mevcut_degerlendirme_sutunlari = [
        sutun
        for sutun in degerlendirme_sutunlari
        if sutun in degerlendirmeler.columns
    ]

    birlesik = aday_geometrileri.merge(
        degerlendirmeler[
            mevcut_degerlendirme_sutunlari
        ],
        on="cell_id",
        how="inner",
        validate="one_to_one",
    )

    birlesik = gpd.GeoDataFrame(
        birlesik,
        geometry="geometry",
        crs=adaylar.crs,
    )

    if birlesik.empty:
        raise ValueError(
            "Aday geometrileri ile değerlendirme "
            "sonuçları eşleştirilemedi.\n"
            "cell_id değerlerini kontrol et."
        )

    birlesik = birlesik.sort_values(
        by="service_need_rank",
        ascending=True,
    ).reset_index(drop=True)

    return birlesik


# ==========================================================
# HİZMET İHTİYACI DOLGU RENGİ
# ==========================================================

def hizmet_ihtiyaci_rengi(
    puan: float,
) -> str:
    """
    Hizmet ihtiyacı puanına göre
    hücrenin dolgu rengini belirler.
    """

    if puan >= 97:
        return "#1e3a8a"

    if puan >= 92:
        return "#1d4ed8"

    if puan >= 87:
        return "#3b82f6"

    if puan >= 82:
        return "#60a5fa"

    return "#bfdbfe"


# ==========================================================
# YER İNCELEME SINIR RENGİ
# ==========================================================

def yer_inceleme_sinir_rengi(
    durum: str,
) -> str:
    """
    Yer inceleme durumuna göre
    hücrenin sınır rengini belirler.
    """

    durum = str(durum).strip()

    if durum == "Ön saha ve parsel incelemesine öncelikli":
        return "#15803d"

    if durum == "İkinci düzey saha incelemesi":
        return "#d97706"

    if durum == "Yeşil alan niteliği araştırılmalı":
        return "#7e22ce"

    if durum == "Yer bulunabilirliği sınırlı olabilir":
        return "#dc2626"

    if durum == "Çevresel kısıt kontrolü gerekli":
        return "#0891b2"

    return "#475569"


# ==========================================================
# ADAY HÜCRE HARİTA STİLİ
# ==========================================================

def aday_stili(
    feature: dict,
) -> dict:
    """
    Her aday hücrenin dolgu ve sınır stilini belirler.

    Dolgu rengi:
    Hizmet ihtiyacı puanını gösterir.

    Sınır rengi:
    Yer inceleme durumunu gösterir.
    """

    ozellikler = feature.get(
        "properties",
        {},
    )

    ham_hizmet_puani = ozellikler.get(
        "service_need_score",
        0,
    )

    try:
        hizmet_puani = float(
            ham_hizmet_puani
        )

    except (TypeError, ValueError):
        hizmet_puani = 0.0

    yer_durumu = str(
        ozellikler.get(
            "site_review_status",
            "",
        )
    )

    return {
        "fillColor": hizmet_ihtiyaci_rengi(
            hizmet_puani
        ),
        "color": yer_inceleme_sinir_rengi(
            yer_durumu
        ),
        "weight": 5,
        "fillOpacity": 0.68,
        "opacity": 1,
    }


# ==========================================================
# VURGULAMA STİLİ
# ==========================================================

def vurgu_stili(
    feature: dict,
) -> dict:
    """
    Fare hücrenin üzerine geldiğinde kullanılacak stil.
    """

    return {
        "weight": 7,
        "color": "#111827",
        "fillOpacity": 0.85,
    }


# ==========================================================
# HARİTA BİLGİ PANELİ
# ==========================================================

def bilgi_paneli_ekle(
    harita: folium.Map,
    ilce_adi: str,
    worldcover_yili: int,
) -> None:
    """
    Haritanın sol üst köşesine açıklama paneli ekler.
    """

    panel_html = f"""
    <div style="
        position: fixed;
        top: 20px;
        left: 55px;
        z-index: 9999;
        width: 390px;
        max-width: calc(100vw - 80px);
        padding: 17px 19px;
        border: 1px solid #dbe2ea;
        border-radius: 13px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 9px 28px rgba(15, 23, 42, 0.16);
        font-family: Arial, sans-serif;
        color: #172033;
    ">
        <div style="
            margin-bottom: 7px;
            font-size: 16px;
            font-weight: 700;
        ">
            {html.escape(ilce_adi)}
            Aday Bölge Karar Destek Haritası
        </div>

        <div style="
            color: #5f6b7a;
            font-size: 11px;
            line-height: 1.55;
        ">
            Dolgu rengi kütüphane hizmet ihtiyacını,
            sınır rengi ise yer inceleme durumunu
            göstermektedir.

            Arazi örtüsü bilgisi ESA WorldCover
            {worldcover_yili} verisine dayanmaktadır.
        </div>
    </div>
    """

    harita.get_root().html.add_child(
        folium.Element(panel_html)
    )


# ==========================================================
# HARİTA LEJANTI
# ==========================================================

def lejant_ekle(
    harita: folium.Map,
) -> None:
    """
    Hizmet ihtiyacı ve yer inceleme renklerini
    açıklayan lejant ekler.
    """

    lejant_html = """
    <div style="
        position: fixed;
        bottom: 28px;
        left: 28px;
        z-index: 9999;
        width: 310px;
        max-width: calc(100vw - 56px);
        padding: 16px;
        border: 1px solid #dbe2ea;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.15);
        font-family: Arial, sans-serif;
        color: #172033;
        font-size: 11px;
        line-height: 1.45;
    ">

        <div style="
            margin-bottom: 9px;
            font-size: 13px;
            font-weight: 700;
        ">
            Harita açıklaması
        </div>

        <div style="
            margin-bottom: 7px;
            font-weight: 700;
        ">
            Dolgu — hizmet ihtiyacı
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:17px;
                height:12px;
                background:#1e3a8a;
            "></span>
            97–100: En yüksek
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:17px;
                height:12px;
                background:#1d4ed8;
            "></span>
            92–96,99: Çok yüksek
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:17px;
                height:12px;
                background:#3b82f6;
            "></span>
            87–91,99: Yüksek
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:17px;
                height:12px;
                background:#60a5fa;
            "></span>
            82–86,99: Orta-yüksek
        </div>

        <hr style="
            margin:11px 0;
            border:0;
            border-top:1px solid #dbe2ea;
        ">

        <div style="
            margin-bottom: 7px;
            font-weight: 700;
        ">
            Sınır — yer inceleme durumu
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:19px;
                border-top:4px solid #15803d;
            "></span>
            Ön saha/parsel incelemesine öncelikli
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:19px;
                border-top:4px solid #d97706;
            "></span>
            İkinci düzey saha incelemesi
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:19px;
                border-top:4px solid #7e22ce;
            "></span>
            Yeşil alan niteliği araştırılmalı
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:19px;
                border-top:4px solid #dc2626;
            "></span>
            Yer bulunabilirliği sınırlı
        </div>

        <div style="display:flex; align-items:center; gap:7px;">
            <span style="
                width:19px;
                border-top:4px solid #0891b2;
            "></span>
            Çevresel kısıt kontrolü
        </div>

    </div>
    """

    harita.get_root().html.add_child(
        folium.Element(lejant_html)
    )


# ==========================================================
# HÜCRE ETİKETLERİ
# ==========================================================

def hucre_etiketlerini_ekle(
    harita: folium.Map,
    birlesik_veri: gpd.GeoDataFrame,
) -> None:
    """
    Hücrelerin ortasına hizmet sırası ve
    hücre kimliği etiketi ekler.
    """

    metrik_veri = birlesik_veri.to_crs(
        ISTANBUL_METRIK_CRS
    )

    etiket_noktalari = (
        metrik_veri.geometry
        .representative_point()
    )

    etiket_noktalari = gpd.GeoSeries(
        etiket_noktalari,
        crs=ISTANBUL_METRIK_CRS,
    ).to_crs(COGRAFI_CRS)

    for sira, (_, kayit) in enumerate(
        birlesik_veri.iterrows()
    ):
        nokta = etiket_noktalari.iloc[sira]

        cell_id = html.escape(
            str(kayit["cell_id"])
        )

        hizmet_sirasi = int(
            kayit["service_need_rank"]
        )

        etiket_html = f"""
        <div style="
            transform: translate(-50%, -50%);
            min-width: 72px;
            padding: 5px 7px;
            border: 2px solid #ffffff;
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.90);
            color: #ffffff;
            text-align: center;
            font-family: Arial, sans-serif;
            box-shadow: 0 3px 9px rgba(0, 0, 0, 0.22);
            white-space: nowrap;
        ">
            <div style="
                font-size: 9px;
                opacity: 0.85;
            ">
                {hizmet_sirasi}. sıra
            </div>

            <div style="
                font-size: 11px;
                font-weight: 700;
            ">
                {cell_id}
            </div>
        </div>
        """

        folium.Marker(
            location=[
                nokta.y,
                nokta.x,
            ],
            icon=folium.DivIcon(
                html=etiket_html,
                icon_size=(0, 0),
                icon_anchor=(0, 0),
            ),
            tooltip=(
                f"{cell_id} — "
                f"{hizmet_sirasi}. hizmet sırası"
            ),
        ).add_to(harita)


# ==========================================================
# ETKİLEŞİMLİ HARİTA OLUŞTURMA
# ==========================================================

def harita_olustur(
    birlesik_veri: gpd.GeoDataFrame,
    ilce_adi: str,
    worldcover_yili: int,
    cikti_yolu: Path,
) -> None:
    """
    Aday hücreleri hizmet ihtiyacı ve yer
    inceleme durumlarıyla birlikte haritada gösterir.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    harita_verisi = birlesik_veri.to_crs(
        COGRAFI_CRS
    )

    metrik_veri = birlesik_veri.to_crs(
        ISTANBUL_METRIK_CRS
    )

    merkez_noktasi = (
        metrik_veri.geometry
        .union_all()
        .centroid
    )

    merkez_cografi = gpd.GeoSeries(
        [merkez_noktasi],
        crs=ISTANBUL_METRIK_CRS,
    ).to_crs(
        COGRAFI_CRS
    ).iloc[0]

    harita = folium.Map(
        location=[
            merkez_cografi.y,
            merkez_cografi.x,
        ],
        zoom_start=13,
        tiles="CartoDB positron",
        control_scale=True,
    )

    aday_katmani = folium.FeatureGroup(
        name="Aday bölge değerlendirmeleri",
        show=True,
    )

    geojson_verisi = harita_verisi.to_json(
        ensure_ascii=False
    )

    folium.GeoJson(
        data=geojson_verisi,
        name="Aday hücreler",
        style_function=aday_stili,
        highlight_function=vurgu_stili,

        tooltip=GeoJsonTooltip(
            fields=[
                "cell_id",
                "service_need_rank",
                "service_need_score",
                "service_need_level",
                "nearest_library_distance_km",
                "site_review_status",
            ],
            aliases=[
                "Hücre:",
                "Hizmet ihtiyacı sırası:",
                "Hizmet ihtiyacı puanı:",
                "Hizmet ihtiyacı seviyesi:",
                "Kütüphaneye uzaklık (km):",
                "Yer inceleme durumu:",
            ],
            localize=True,
            sticky=True,
        ),

        popup=GeoJsonPopup(
            fields=[
                "cell_id",
                "service_need_rank",
                "service_need_score",
                "service_need_level",
                "nearest_library_name",
                "nearest_library_distance_km",
                "site_review_status",
                "site_review_explanation",
                "built_up_pct",
                "vegetation_pct",
                "open_bare_pct",
                "water_wetland_pct",
                "worldcover_coverage_pct",
                "evaluation_text",
            ],
            aliases=[
                "Hücre:",
                "Hizmet ihtiyacı sırası:",
                "Hizmet ihtiyacı puanı:",
                "Hizmet ihtiyacı:",
                "En yakın kütüphane:",
                "Kütüphaneye uzaklık (km):",
                "Yer inceleme durumu:",
                "Yer inceleme açıklaması:",
                "Yapılaşmış alan (%):",
                "Bitkisel / yeşil alan (%):",
                "Açık / çıplak alan (%):",
                "Su / sulak alan (%):",
                "WorldCover kapsaması (%):",
                "Genel değerlendirme:",
            ],
            labels=True,
            localize=True,
            style=(
                "background-color: white; "
                "color: #172033; "
                "font-family: Arial; "
                "font-size: 12px; "
                "max-width: 430px;"
            ),
        ),
    ).add_to(aday_katmani)

    aday_katmani.add_to(harita)

    hucre_etiketlerini_ekle(
        harita,
        harita_verisi,
    )

    toplam_sinir = harita_verisi.total_bounds

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
        ],
        padding=(35, 35),
    )

    Fullscreen(
        position="topright",
        title="Tam ekran",
        title_cancel="Tam ekrandan çık",
        force_separate_button=True,
    ).add_to(harita)

    MiniMap(
        toggle_display=True,
        position="bottomright",
    ).add_to(harita)

    bilgi_paneli_ekle(
        harita,
        ilce_adi,
        worldcover_yili,
    )

    lejant_ekle(harita)

    folium.LayerControl(
        collapsed=False
    ).add_to(harita)

    harita.save(str(cikti_yolu))


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    birlesik_veri: gpd.GeoDataFrame,
    ilce_adi: str,
    yollar: dict[str, Path],
) -> None:
    """
    Harita üretim sonucunu terminalde özetler.
    """

    print()
    print("=" * 95)
    print("ADAY BÖLGE DEĞERLENDİRME HARİTASI HAZIRLANDI")
    print("=" * 95)

    print()
    print("İlçe:", ilce_adi)

    print(
        "Haritada gösterilen aday hücre:",
        len(birlesik_veri),
    )

    print()
    print("Harita sıralaması:")

    for kayit in birlesik_veri.itertuples():
        print()
        print(
            f"  {int(kayit.service_need_rank)}. sıra "
            f"— {kayit.cell_id}"
        )

        print(
            f"    Hizmet ihtiyacı: "
            f"{kayit.service_need_score:.2f}"
        )

        print(
            f"    Yer inceleme durumu: "
            f"{kayit.site_review_status}"
        )

    print()
    print("Birleştirilmiş harita GeoJSON'u:")
    print(f"  {yollar['birlesik_geojson']}")

    print()
    print("Etkileşimli karar destek haritası:")
    print(f"  {yollar['harita_html']}")

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Aday geometrileriyle iki eksenli değerlendirme
    sonuçlarını birleştirip etkileşimli harita üretir.
    """

    argumanlar = argumanlari_oku()

    ilce_adi = argumanlar.ilce
    ilce_slug = slug_olustur(ilce_adi)

    yollar = dosya_yollarini_olustur(
        ilce_slug
    )

    print()
    print("Analiz ayarları:")
    print(f"  İlçe: {ilce_adi}")
    print(f"  WorldCover yılı: {argumanlar.yil}")

    print()
    print("Aday hücre geometrileri okunuyor...")

    adaylar = aday_hucreleri_oku(
        yollar["aday_hucre_geojson"]
    )

    print(
        "İki eksenli değerlendirme sonuçları okunuyor..."
    )

    degerlendirmeler = degerlendirme_sonuclarini_oku(
        yollar["degerlendirme_csv"]
    )

    print(
        "Geometriler ve değerlendirme sonuçları "
        "birleştiriliyor..."
    )

    birlesik_veri = verileri_birlestir(
        adaylar,
        degerlendirmeler,
    )

    yollar["birlesik_geojson"].parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    geojson_metni = (
        birlesik_veri
        .to_crs(COGRAFI_CRS)
        .to_json(ensure_ascii=False)
    )

    yollar["birlesik_geojson"].write_text(
        geojson_metni,
        encoding="utf-8",
    )

    print(
        "Etkileşimli aday değerlendirme "
        "haritası oluşturuluyor..."
    )

    harita_olustur(
        birlesik_veri,
        ilce_adi,
        argumanlar.yil,
        yollar["harita_html"],
    )

    terminal_ozetini_yazdir(
        birlesik_veri,
        ilce_adi,
        yollar,
    )


if __name__ == "__main__":
    main()
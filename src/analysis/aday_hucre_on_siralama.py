from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

from folium.features import GeoJsonPopup, GeoJsonTooltip


# ==========================================================
# PROJE YOLLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

GIRDI_GEOJSON_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "hizmet_boslugu_hucreleri.geojson"
)

TUM_ADAYLAR_CSV_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "aday_hucre_on_siralama.csv"
)

ILCE_BAZLI_ILK_ADAYLAR_CSV_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "aday_hucre_ilce_bazli_ilk5.csv"
)

HARITA_CIKTI_YOLU = (
    PROJE_KOKU
    / "frontend"
    / "aday_hucre_on_siralama_haritasi.html"
)


# ==========================================================
# ANALİZ AYARLARI
# ==========================================================

MESAFE_AGIRLIGI = 0.70

ILCE_ONCELIK_AGIRLIGI = 0.30

ILCE_BASINA_ADAY_SAYISI = 5

COGRAFI_KOORDINAT_SISTEMI = "EPSG:4326"


# ==========================================================
# VERİYİ OKUMA
# ==========================================================

def veriyi_oku() -> gpd.GeoDataFrame:
    """
    Hizmet boşluğu analizinde üretilen hücreleri
    GeoJSON dosyasından okur.
    """

    if not GIRDI_GEOJSON_YOLU.exists():
        raise FileNotFoundError(
            "Hizmet boşluğu GeoJSON dosyası bulunamadı:\n"
            f"{GIRDI_GEOJSON_YOLU}\n\n"
            "Önce hizmet_boslugu_analizi.py dosyasını çalıştır."
        )

    hucreler = gpd.read_file(
        GIRDI_GEOJSON_YOLU
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "population_2025",
        "facility_count",
        "priority_score",
        "priority_rank",
        "cell_area_ratio",
        "center_latitude",
        "center_longitude",
        "nearest_library_name",
        "nearest_library_distance_km",
        "service_gap_class",
        "candidate_review",
        "geometry",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in hucreler.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Girdi dosyasında eksik sütunlar var:\n"
            + "\n".join(eksik_sutunlar)
        )

    if hucreler.crs is None:
        hucreler = hucreler.set_crs(
            COGRAFI_KOORDINAT_SISTEMI
        )

    return hucreler


# ==========================================================
# MIN-MAX NORMALİZASYONU
# ==========================================================

def min_max_100(
    seri: pd.Series,
) -> pd.Series:
    """
    Bir sayısal seriyi 0 ile 100 arasına dönüştürür.

    En küçük değer 0,
    en büyük değer 100 olur.
    """

    sayisal_seri = pd.to_numeric(
        seri,
        errors="coerce",
    )

    minimum_deger = sayisal_seri.min()

    maksimum_deger = sayisal_seri.max()

    if (
        pd.isna(minimum_deger)
        or pd.isna(maksimum_deger)
    ):
        raise ValueError(
            "Normalizasyon için geçerli "
            "sayısal veri bulunamadı."
        )

    if maksimum_deger == minimum_deger:
        return pd.Series(
            100.0,
            index=sayisal_seri.index,
        )

    normalize_edilmis_seri = (
        (
            sayisal_seri
            - minimum_deger
        )
        / (
            maksimum_deger
            - minimum_deger
        )
        * 100
    )

    return normalize_edilmis_seri


# ==========================================================
# ADAY HÜCRELERİ HAZIRLAMA
# ==========================================================

def aday_hucreleri_hazirla(
    hucreler: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    En yakın doğrulanmış İBB kütüphanesine
    3 kilometreden uzak olan hücreleri seçer.

    İki farklı karşılaştırma puanı hesaplar:

    1. Genel ön eleme puanı:
       Bütün ilçelerdeki adayları aynı ölçekte
       karşılaştırır.

    2. İlçe içi ön eleme puanı:
       Her hücreyi yalnızca kendi ilçesindeki
       diğer aday hücrelerle karşılaştırır.
    """

    adaylar = hucreler[
        hucreler[
            "candidate_review"
        ]
        .astype(str)
        .str.strip()
        .eq("Evet")
    ].copy()

    if adaylar.empty:
        raise ValueError(
            "Ayrıntılı inceleme adayı "
            "hücre bulunamadı."
        )

    adaylar[
        "nearest_library_distance_km"
    ] = pd.to_numeric(
        adaylar[
            "nearest_library_distance_km"
        ],
        errors="coerce",
    )

    adaylar[
        "priority_score"
    ] = pd.to_numeric(
        adaylar[
            "priority_score"
        ],
        errors="coerce",
    )

    adaylar = adaylar.dropna(
        subset=[
            "nearest_library_distance_km",
            "priority_score",
        ]
    ).copy()

    if adaylar.empty:
        raise ValueError(
            "Puanlama için geçerli aday hücre kalmadı."
        )


    # ======================================================
    # 1. GENEL MESAFE PUANI
    # ======================================================

    # Bütün 475 aday hücre aynı ölçekte karşılaştırılır.
    # İstanbul genelindeki en uzak aday 100 puana yaklaşır.

    adaylar[
        "global_distance_score"
    ] = min_max_100(
        adaylar[
            "nearest_library_distance_km"
        ]
    )


    # ======================================================
    # 2. İLÇE İÇİ MESAFE PUANI
    # ======================================================

    # Her hücre yalnızca kendi ilçesindeki diğer
    # aday hücrelerle karşılaştırılır.
    #
    # Böylece Pendik'teki çok yüksek mesafeler,
    # diğer ilçelerin harita renklerini bastırmaz.

    adaylar[
        "district_distance_score"
    ] = (
        adaylar
        .groupby(
            "district_name"
        )[
            "nearest_library_distance_km"
        ]
        .transform(
            min_max_100
        )
    )


    # ======================================================
    # 3. GENEL ÖN ELEME PUANI
    # ======================================================

    # Bu puan bütün ilçelerdeki adayların
    # İstanbul genelinde karşılaştırılması içindir.

    adaylar[
        "global_preliminary_score"
    ] = (
        adaylar[
            "global_distance_score"
        ]
        * MESAFE_AGIRLIGI
        +
        adaylar[
            "priority_score"
        ]
        * ILCE_ONCELIK_AGIRLIGI
    )


    # ======================================================
    # 4. İLÇE İÇİ ÖN ELEME PUANI
    # ======================================================

    # Bu puan, ilçenin kendi aday hücrelerini
    # sıralamak ve haritada renklendirmek için kullanılır.

    adaylar[
        "preliminary_need_score"
    ] = (
        adaylar[
            "district_distance_score"
        ]
        * MESAFE_AGIRLIGI
        +
        adaylar[
            "priority_score"
        ]
        * ILCE_ONCELIK_AGIRLIGI
    )


    # ======================================================
    # PUANLARI YUVARLAMA
    # ======================================================

    puan_sutunlari = [
        "global_distance_score",
        "district_distance_score",
        "global_preliminary_score",
        "preliminary_need_score",
    ]

    adaylar[
        puan_sutunlari
    ] = (
        adaylar[
            puan_sutunlari
        ]
        .round(3)
    )


    # ======================================================
    # GENEL ADAY SIRASI
    # ======================================================

    adaylar = adaylar.sort_values(
        by=[
            "global_preliminary_score",
            "nearest_library_distance_km",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )

    adaylar[
        "global_candidate_rank"
    ] = range(
        1,
        len(adaylar) + 1,
    )


    # ======================================================
    # İLÇE İÇİ ADAY SIRASI
    # ======================================================

    adaylar[
        "district_candidate_rank"
    ] = (
        adaylar
        .groupby(
            "district_name"
        )[
            "preliminary_need_score"
        ]
        .rank(
            method="first",
            ascending=False,
        )
        .astype(int)
    )


    # Her ilçeden ilk beş hücre,
    # sonraki uydu görüntüsü incelemesine alınır.

    adaylar[
        "selected_for_next_stage"
    ] = (
        adaylar[
            "district_candidate_rank"
        ]
        <= ILCE_BASINA_ADAY_SAYISI
    )

    return gpd.GeoDataFrame(
        adaylar,
        geometry="geometry",
        crs=hucreler.crs,
    )


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    adaylar: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Bütün aday hücreleri ve her ilçeden seçilen
    ilk beş hücreyi ayrı CSV dosyalarına kaydeder.
    """

    TUM_ADAYLAR_CSV_YOLU.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    csv_sutunlari = [
        "global_candidate_rank",
        "district_candidate_rank",
        "cell_id",
        "district_name",
        "population_2025",
        "facility_count",
        "priority_rank",
        "priority_score",
        "nearest_library_name",
        "nearest_library_distance_km",
        "global_distance_score",
        "district_distance_score",
        "global_preliminary_score",
        "preliminary_need_score",
        "cell_area_ratio",
        "center_latitude",
        "center_longitude",
        "service_gap_class",
        "selected_for_next_stage",
    ]

    adaylar[
        csv_sutunlari
    ].to_csv(
        TUM_ADAYLAR_CSV_YOLU,
        index=False,
        encoding="utf-8-sig",
    )

    ilce_bazli_ilk_adaylar = adaylar[
        adaylar[
            "selected_for_next_stage"
        ]
    ].copy()

    ilce_bazli_ilk_adaylar = (
        ilce_bazli_ilk_adaylar
        .sort_values(
            by=[
                "priority_rank",
                "district_candidate_rank",
            ],
            ascending=[
                True,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    ilce_bazli_ilk_adaylar[
        csv_sutunlari
    ].to_csv(
        ILCE_BAZLI_ILK_ADAYLAR_CSV_YOLU,
        index=False,
        encoding="utf-8-sig",
    )

    return ilce_bazli_ilk_adaylar


# ==========================================================
# PUAN RENGİ
# ==========================================================

def puan_rengi(
    puan: float,
) -> str:
    """
    İlçe içi ön eleme puanını
    haritada kullanılacak renge dönüştürür.
    """

    if puan >= 80:
        return "#991b1b"

    if puan >= 65:
        return "#dc2626"

    if puan >= 50:
        return "#f97316"

    return "#facc15"


# ==========================================================
# HARİTA BİLGİ PANELİ
# ==========================================================

def bilgi_paneli_ekle(
    harita: folium.Map,
) -> None:
    """
    Haritanın sol üst bölümüne
    analiz açıklaması ekler.
    """

    panel_html = f"""
    <div style="
        position: fixed;
        top: 18px;
        left: 55px;
        z-index: 9999;
        width: 370px;
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
            Aday Hücre Ön Sıralaması
        </div>

        <div style="
            font-size: 11px;
            line-height: 1.6;
            color: #5e6878;
        ">
            Her öncelikli ilçeden en yüksek puanlı
            {ILCE_BASINA_ADAY_SAYISI} hücre gösterilmektedir.
            Harita renkleri; hücrenin kendi ilçesindeki
            göreli kütüphane uzaklığı ve ilçe öncelik
            puanı kullanılarak hesaplanmıştır.
            Sonuçlar nihai yer seçimi değildir.
        </div>
    </div>
    """

    harita.get_root().html.add_child(
        folium.Element(
            panel_html
        )
    )


# ==========================================================
# HARİTA LEJANTI
# ==========================================================

def lejant_ekle(
    harita: folium.Map,
) -> None:
    """
    Haritanın sağ alt bölümüne
    puan renklerinin açıklamasını ekler.
    """

    lejant_html = """
    <div style="
        position: fixed;
        right: 20px;
        bottom: 25px;
        z-index: 9999;
        width: 250px;
        padding: 15px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.16);
        font-family: Arial, sans-serif;
        font-size: 11px;
        color: #172033;
    ">
        <div style="
            font-weight: 700;
            margin-bottom: 10px;
        ">
            İlçe içi ön eleme puanı
        </div>

        <div style="margin-bottom: 7px;">
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 7px;
                background: #991b1b;
                border-radius: 3px;
                vertical-align: middle;
            "></span>

            80–100: Çok yüksek
        </div>

        <div style="margin-bottom: 7px;">
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 7px;
                background: #dc2626;
                border-radius: 3px;
                vertical-align: middle;
            "></span>

            65–80: Yüksek
        </div>

        <div style="margin-bottom: 7px;">
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 7px;
                background: #f97316;
                border-radius: 3px;
                vertical-align: middle;
            "></span>

            50–65: Orta-yüksek
        </div>

        <div>
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 7px;
                background: #facc15;
                border-radius: 3px;
                vertical-align: middle;
            "></span>

            50 altı: Ön inceleme
        </div>
    </div>
    """

    harita.get_root().html.add_child(
        folium.Element(
            lejant_html
        )
    )


# ==========================================================
# HARİTA OLUŞTURMA
# ==========================================================

def harita_olustur(
    tum_adaylar: gpd.GeoDataFrame,
    secilen_adaylar: gpd.GeoDataFrame,
) -> None:
    """
    Bütün 3 kilometre üzerindeki hücreleri
    arka planda gri olarak gösterir.

    Her ilçeden seçilen ilk beş hücreyi ise
    renkli ve vurgulu şekilde gösterir.
    """

    HARITA_CIKTI_YOLU.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tum_adaylar_cografi = (
        tum_adaylar.to_crs(
            COGRAFI_KOORDINAT_SISTEMI
        )
    )

    secilen_adaylar_cografi = (
        secilen_adaylar.to_crs(
            COGRAFI_KOORDINAT_SISTEMI
        )
    )

    harita = folium.Map(
        location=[
            41.02,
            28.97,
        ],
        zoom_start=10,
        tiles="CartoDB positron",
        control_scale=True,
    )


    # ------------------------------------------------------
    # BÜTÜN 3 KM ÜZERİNDEKİ ADAY HÜCRELER
    # ------------------------------------------------------

    folium.GeoJson(
        data=tum_adaylar_cografi[
            [
                "cell_id",
                "district_name",
                "nearest_library_distance_km",
                "geometry",
            ]
        ].to_json(
            ensure_ascii=False
        ),
        name="Bütün 3 km üzeri hücreler",
        style_function=lambda feature: {
            "fillColor": "#94a3b8",
            "color": "#ffffff",
            "weight": 0.4,
            "fillOpacity": 0.14,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "district_name",
                "nearest_library_distance_km",
            ],
            aliases=[
                "İlçe:",
                "En yakın kütüphane uzaklığı (km):",
            ],
            localize=True,
            sticky=True,
        ),
    ).add_to(
        harita
    )


    # ------------------------------------------------------
    # İLÇE BAZINDA SEÇİLEN İLK BEŞ HÜCRE
    # ------------------------------------------------------

    folium.GeoJson(
        data=secilen_adaylar_cografi.to_json(
            ensure_ascii=False
        ),
        name="İlçe bazında ilk 5 aday",
        style_function=lambda feature: {
            "fillColor": puan_rengi(
                float(
                    feature[
                        "properties"
                    ][
                        "preliminary_need_score"
                    ]
                )
            ),
            "color": "#111827",
            "weight": 1.5,
            "fillOpacity": 0.72,
        },
        highlight_function=lambda feature: {
            "color": "#000000",
            "weight": 3,
            "fillOpacity": 0.90,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "district_name",
                "district_candidate_rank",
                "preliminary_need_score",
            ],
            aliases=[
                "İlçe:",
                "İlçe içi aday sırası:",
                "İlçe içi ön eleme puanı:",
            ],
            localize=True,
            sticky=True,
        ),
        popup=GeoJsonPopup(
            fields=[
                "cell_id",
                "district_name",
                "district_candidate_rank",
                "global_candidate_rank",
                "priority_score",
                "nearest_library_name",
                "nearest_library_distance_km",
                "global_distance_score",
                "district_distance_score",
                "global_preliminary_score",
                "preliminary_need_score",
            ],
            aliases=[
                "Hücre:",
                "İlçe:",
                "İlçe içi aday sırası:",
                "Genel aday sırası:",
                "İlçe öncelik puanı:",
                "En yakın kütüphane:",
                "Kütüphaneye uzaklık (km):",
                "Genel mesafe puanı:",
                "İlçe içi mesafe puanı:",
                "Genel ön eleme puanı:",
                "İlçe içi ön eleme puanı:",
            ],
            labels=True,
            localize=True,
        ),
    ).add_to(
        harita
    )


    # ------------------------------------------------------
    # SEÇİLEN ADAYLARIN MERKEZ NOKTALARI
    # ------------------------------------------------------

    for aday in (
        secilen_adaylar_cografi.itertuples()
    ):

        folium.CircleMarker(
            location=[
                aday.center_latitude,
                aday.center_longitude,
            ],
            radius=5,
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color=puan_rengi(
                aday.preliminary_need_score
            ),
            fill_opacity=1,
            tooltip=(
                f"{aday.district_name} – "
                f"{aday.district_candidate_rank}. aday"
            ),
        ).add_to(
            harita
        )


    # ------------------------------------------------------
    # HARİTAYI SEÇİLEN ADAYLARA SIĞDIRMA
    # ------------------------------------------------------

    toplam_sinir = (
        secilen_adaylar_cografi.total_bounds
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
        harita
    )

    lejant_ekle(
        harita
    )

    folium.LayerControl(
        collapsed=False
    ).add_to(
        harita
    )

    harita.save(
        HARITA_CIKTI_YOLU
    )


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    tum_adaylar: gpd.GeoDataFrame,
    secilen_adaylar: gpd.GeoDataFrame,
) -> None:
    """
    Aday hücre sıralamasını terminalde özetler.
    """

    print()
    print("=" * 95)
    print("ADAY HÜCRE ÖN SIRALAMASI TAMAMLANDI")
    print("=" * 95)

    print()
    print(
        "Toplam 3 km üzeri aday hücre:",
        len(tum_adaylar),
    )

    print(
        "Sonraki aşama için seçilen hücre:",
        len(secilen_adaylar),
    )

    print()
    print(
        "İlçe bazında en güçlü adaylar:"
    )

    en_iyi_adaylar = (
        secilen_adaylar[
            secilen_adaylar[
                "district_candidate_rank"
            ]
            == 1
        ]
        .sort_values(
            by="priority_rank"
        )
    )

    for aday in en_iyi_adaylar.itertuples():

        print()
        print(
            f"  {aday.district_name}"
        )

        print(
            f"    Hücre: "
            f"{aday.cell_id}"
        )

        print(
            f"    En yakın kütüphane uzaklığı: "
            f"{aday.nearest_library_distance_km:.2f} km"
        )

        print(
            f"    Genel mesafe puanı: "
            f"{aday.global_distance_score:.2f}"
        )

        print(
            f"    İlçe içi mesafe puanı: "
            f"{aday.district_distance_score:.2f}"
        )

        print(
            f"    Genel ön eleme puanı: "
            f"{aday.global_preliminary_score:.2f}"
        )

        print(
            f"    İlçe içi ön eleme puanı: "
            f"{aday.preliminary_need_score:.2f}"
        )

        print(
            f"    Merkez koordinatı: "
            f"{aday.center_latitude}, "
            f"{aday.center_longitude}"
        )

    print()
    print(
        "Bütün adayların CSV çıktısı:"
    )

    print(
        f"  {TUM_ADAYLAR_CSV_YOLU}"
    )

    print()
    print(
        "İlçe bazında ilk 5 aday CSV çıktısı:"
    )

    print(
        f"  {ILCE_BAZLI_ILK_ADAYLAR_CSV_YOLU}"
    )

    print()
    print(
        "Etkileşimli aday haritası:"
    )

    print(
        f"  {HARITA_CIKTI_YOLU}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Aday hücre ön sıralamasının
    bütün adımlarını çalıştırır.
    """

    print()
    print(
        "Hizmet boşluğu hücreleri okunuyor..."
    )

    hucreler = veriyi_oku()

    print(
        "3 km üzerindeki aday hücreler seçiliyor..."
    )

    tum_adaylar = aday_hucreleri_hazirla(
        hucreler
    )

    print(
        "Aday hücre sıralamaları kaydediliyor..."
    )

    secilen_adaylar = ciktilari_kaydet(
        tum_adaylar
    )

    print(
        "Etkileşimli aday hücre haritası oluşturuluyor..."
    )

    harita_olustur(
        tum_adaylar,
        secilen_adaylar,
    )

    terminal_ozetini_yazdir(
        tum_adaylar,
        secilen_adaylar,
    )


if __name__ == "__main__":
    main()
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# ==========================================================
# PROJE YOLLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

GIRDI_CSV_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "hizmet_boslugu_hucreleri.csv"
)

OZET_CSV_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "hizmet_boslugu_ilce_ozeti.csv"
)

GRAFIK_KLASORU = (
    PROJE_KOKU
    / "frontend"
    / "assets"
)

GRAFIK_CIKTI_YOLU = (
    GRAFIK_KLASORU
    / "hizmet_boslugu_ilce_ozeti.png"
)


# ==========================================================
# HİZMET SINIFLARI
# ==========================================================

HIZMETE_YAKIN = "Hizmete yakın"
ORTA_UZAKLIK = "Orta uzaklık"
HIZMET_ACIGI_YUKSEK = "Hizmet açığı yüksek"
GUCLU_ADAY = "Güçlü aday inceleme alanı"


# ==========================================================
# VERİYİ OKUMA
# ==========================================================

def veriyi_oku() -> pd.DataFrame:
    """
    Hücre bazlı hizmet boşluğu analizini CSV dosyasından okur.
    """

    if not GIRDI_CSV_YOLU.exists():
        raise FileNotFoundError(
            "Hizmet boşluğu hücre dosyası bulunamadı:\n"
            f"{GIRDI_CSV_YOLU}\n\n"
            "Önce hizmet_boslugu_analizi.py dosyasını çalıştır."
        )

    dataframe = pd.read_csv(
        GIRDI_CSV_YOLU
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "population_2025",
        "facility_count",
        "priority_score",
        "priority_rank",
        "cell_area_km2",
        "nearest_library_distance_km",
        "service_gap_class",
        "candidate_review",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in dataframe.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Girdi dosyasında eksik sütunlar var:\n"
            + "\n".join(eksik_sutunlar)
        )

    return dataframe


# ==========================================================
# YARDIMCI SÜTUNLARI EKLEME
# ==========================================================

def yardimci_sutunlari_ekle(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    İlçe özeti için gerekli mantıksal ve alan sütunlarını ekler.
    """

    sonuc = dataframe.copy()

    sonuc["candidate_flag"] = (
        sonuc["candidate_review"]
        .astype(str)
        .str.strip()
        .eq("Evet")
    )

    sonuc["distance_over_2km_flag"] = (
        sonuc["nearest_library_distance_km"]
        > 2
    )

    sonuc["distance_over_3km_flag"] = (
        sonuc["nearest_library_distance_km"]
        > 3
    )

    sonuc["candidate_area_km2"] = (
        sonuc["cell_area_km2"]
        * sonuc["candidate_flag"].astype(int)
    )

    sonuc["distance_over_2km_area_km2"] = (
        sonuc["cell_area_km2"]
        * sonuc["distance_over_2km_flag"].astype(int)
    )

    sonuc["distance_over_3km_area_km2"] = (
        sonuc["cell_area_km2"]
        * sonuc["distance_over_3km_flag"].astype(int)
    )

    return sonuc


# ==========================================================
# İLÇE ÖZETİNİ OLUŞTURMA
# ==========================================================

def ilce_ozetini_olustur(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Hücre bazındaki sonuçları ilçe bazında özetler.
    """

    ozet = (
        dataframe
        .groupby(
            "district_name",
            as_index=False,
        )
        .agg(
            priority_rank=(
                "priority_rank",
                "first",
            ),
            priority_score=(
                "priority_score",
                "first",
            ),
            population_2025=(
                "population_2025",
                "first",
            ),
            facility_count=(
                "facility_count",
                "first",
            ),
            total_cells=(
                "cell_id",
                "count",
            ),
            average_distance_km=(
                "nearest_library_distance_km",
                "mean",
            ),
            median_distance_km=(
                "nearest_library_distance_km",
                "median",
            ),
            maximum_distance_km=(
                "nearest_library_distance_km",
                "max",
            ),
            total_analysis_area_km2=(
                "cell_area_km2",
                "sum",
            ),
            candidate_cells=(
                "candidate_flag",
                "sum",
            ),
            candidate_area_km2=(
                "candidate_area_km2",
                "sum",
            ),
            distance_over_2km_area_km2=(
                "distance_over_2km_area_km2",
                "sum",
            ),
            distance_over_3km_area_km2=(
                "distance_over_3km_area_km2",
                "sum",
            ),
        )
    )

    # ------------------------------------------------------
    # HİZMET SINIFI HÜCRE SAYILARI
    # ------------------------------------------------------

    sinif_sayilari = (
        dataframe
        .groupby(
            [
                "district_name",
                "service_gap_class",
            ]
        )
        .size()
        .unstack(
            fill_value=0
        )
        .reset_index()
    )

    sinif_sutun_eslesmeleri = {
        HIZMETE_YAKIN: "near_service_cells",
        ORTA_UZAKLIK: "medium_distance_cells",
        HIZMET_ACIGI_YUKSEK: "high_gap_cells",
        GUCLU_ADAY: "strong_candidate_cells",
    }

    for eski_sutun, yeni_sutun in (
        sinif_sutun_eslesmeleri.items()
    ):
        if eski_sutun not in sinif_sayilari.columns:
            sinif_sayilari[eski_sutun] = 0

        sinif_sayilari = sinif_sayilari.rename(
            columns={
                eski_sutun: yeni_sutun,
            }
        )

    tutulacak_sinif_sutunlari = [
        "district_name",
        "near_service_cells",
        "medium_distance_cells",
        "high_gap_cells",
        "strong_candidate_cells",
    ]

    ozet = ozet.merge(
        sinif_sayilari[
            tutulacak_sinif_sutunlari
        ],
        on="district_name",
        how="left",
    )

    # ------------------------------------------------------
    # ORANLAR
    # ------------------------------------------------------

    ozet["candidate_cell_ratio_pct"] = (
        ozet["candidate_cells"]
        / ozet["total_cells"]
        * 100
    )

    ozet["candidate_area_ratio_pct"] = (
        ozet["candidate_area_km2"]
        / ozet["total_analysis_area_km2"]
        * 100
    )

    ozet["distance_over_2km_area_ratio_pct"] = (
        ozet["distance_over_2km_area_km2"]
        / ozet["total_analysis_area_km2"]
        * 100
    )

    ozet["distance_over_3km_area_ratio_pct"] = (
        ozet["distance_over_3km_area_km2"]
        / ozet["total_analysis_area_km2"]
        * 100
    )

    # ------------------------------------------------------
    # SAYILARI YUVARLAMA
    # ------------------------------------------------------

    yuvarlanacak_sutunlar = [
        "priority_score",
        "average_distance_km",
        "median_distance_km",
        "maximum_distance_km",
        "total_analysis_area_km2",
        "candidate_area_km2",
        "distance_over_2km_area_km2",
        "distance_over_3km_area_km2",
        "candidate_cell_ratio_pct",
        "candidate_area_ratio_pct",
        "distance_over_2km_area_ratio_pct",
        "distance_over_3km_area_ratio_pct",
    ]

    ozet[yuvarlanacak_sutunlar] = (
        ozet[yuvarlanacak_sutunlar]
        .round(2)
    )

    ozet = ozet.sort_values(
        by="priority_rank",
        ascending=True,
    ).reset_index(
        drop=True
    )

    return ozet


# ==========================================================
# CSV KAYDETME
# ==========================================================

def ozeti_kaydet(
    ozet: pd.DataFrame,
) -> None:
    """
    İlçe özet tablosunu CSV olarak kaydeder.
    """

    OZET_CSV_YOLU.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ozet.to_csv(
        OZET_CSV_YOLU,
        index=False,
        encoding="utf-8-sig",
    )


# ==========================================================
# GRAFİK OLUŞTURMA
# ==========================================================

def grafik_olustur(
    ozet: pd.DataFrame,
) -> None:
    """
    İlçelerin 3 km üzerindeki aday alan oranlarını
    yatay çubuk grafik olarak gösterir.
    """

    GRAFIK_KLASORU.mkdir(
        parents=True,
        exist_ok=True,
    )

    grafik_verisi = ozet.sort_values(
        by="candidate_area_ratio_pct",
        ascending=True,
    )

    fig, eksen = plt.subplots(
        figsize=(10, 6)
    )

    cubuklar = eksen.barh(
        grafik_verisi["district_name"],
        grafik_verisi["candidate_area_ratio_pct"],
    )

    eksen.set_title(
        "Öncelikli İlçelerde Kütüphane Hizmet Boşluğu"
    )

    eksen.set_xlabel(
        "3 km üzerindeki aday inceleme alanı (%)"
    )

    eksen.set_ylabel(
        "İlçe"
    )

    eksen.set_xlim(
        0,
        100,
    )

    eksen.grid(
        axis="x",
        alpha=0.25,
    )

    for cubuk, oran in zip(
        cubuklar,
        grafik_verisi[
            "candidate_area_ratio_pct"
        ],
    ):
        eksen.text(
            oran + 1,
            cubuk.get_y()
            + cubuk.get_height() / 2,
            f"%{oran:.1f}",
            va="center",
            fontsize=10,
        )

    fig.text(
        0.5,
        0.01,
        (
            "Not: Aday alanlar, yalnızca doğrulanmış İBB "
            "kütüphanelerine olan doğrusal uzaklığa göre "
            "belirlenen ilk analiz sonucudur."
        ),
        ha="center",
        fontsize=9,
    )

    fig.tight_layout(
        rect=[
            0,
            0.05,
            1,
            1,
        ]
    )

    fig.savefig(
        GRAFIK_CIKTI_YOLU,
        dpi=180,
        bbox_inches="tight",
    )

    plt.close(
        fig
    )


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    ozet: pd.DataFrame,
) -> None:
    """
    İlçe karşılaştırmasını terminalde okunabilir biçimde gösterir.
    """

    print()
    print("=" * 90)
    print("İLÇE BAZINDA KÜTÜPHANE HİZMET BOŞLUĞU ÖZETİ")
    print("=" * 90)

    for kayit in ozet.itertuples():

        print()
        print(
            f"{int(kayit.priority_rank)}. "
            f"{kayit.district_name}"
        )

        print(
            f"   Öncelik puanı: "
            f"{kayit.priority_score:.3f}"
        )

        print(
            f"   Toplam analiz hücresi: "
            f"{int(kayit.total_cells)}"
        )

        print(
            f"   Ortalama kütüphane uzaklığı: "
            f"{kayit.average_distance_km:.2f} km"
        )

        print(
            f"   En uzak analiz hücresi: "
            f"{kayit.maximum_distance_km:.2f} km"
        )

        print(
            f"   3 km üzerindeki hücre: "
            f"{int(kayit.candidate_cells)}"
        )

        print(
            f"   3 km üzerindeki alan oranı: "
            f"%{kayit.candidate_area_ratio_pct:.2f}"
        )

    print()
    print("-" * 90)

    en_yuksek_aday_orani = ozet.loc[
        ozet[
            "candidate_area_ratio_pct"
        ].idxmax()
    ]

    en_yuksek_ortalama_mesafe = ozet.loc[
        ozet[
            "average_distance_km"
        ].idxmax()
    ]

    print(
        "Aday alan oranı en yüksek ilçe:"
    )

    print(
        f"  {en_yuksek_aday_orani['district_name']} "
        f"(%{en_yuksek_aday_orani['candidate_area_ratio_pct']:.2f})"
    )

    print()
    print(
        "Ortalama kütüphane uzaklığı en yüksek ilçe:"
    )

    print(
        f"  {en_yuksek_ortalama_mesafe['district_name']} "
        f"({en_yuksek_ortalama_mesafe['average_distance_km']:.2f} km)"
    )

    print()
    print(
        "CSV çıktısı:"
    )

    print(
        f"  {OZET_CSV_YOLU}"
    )

    print()
    print(
        "Grafik çıktısı:"
    )

    print(
        f"  {GRAFIK_CIKTI_YOLU}"
    )

    print()
    print("=" * 90)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    İlçe bazında hizmet boşluğu özetini oluşturur.
    """

    print()
    print(
        "Hücre bazlı hizmet boşluğu verisi okunuyor..."
    )

    dataframe = veriyi_oku()

    print(
        "Yardımcı analiz sütunları hazırlanıyor..."
    )

    dataframe = yardimci_sutunlari_ekle(
        dataframe
    )

    print(
        "İlçe bazında özet hesaplanıyor..."
    )

    ozet = ilce_ozetini_olustur(
        dataframe
    )

    print(
        "Özet CSV dosyası kaydediliyor..."
    )

    ozeti_kaydet(
        ozet
    )

    print(
        "Karşılaştırma grafiği oluşturuluyor..."
    )

    grafik_olustur(
        ozet
    )

    terminal_ozetini_yazdir(
        ozet
    )


if __name__ == "__main__":
    main()
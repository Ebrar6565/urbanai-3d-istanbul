from pathlib import Path
import json
import sqlite3

import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

veritabani_yolu = Path(
    "data/database/urbanai.db"
)

nufus_veri_yolu = Path(
    "data/processed/ibb_2025_ilce_nufuslari.csv"
)

ilce_geojson_yolu = Path(
    "data/raw/istanbul_ilce_sinirlari.geojson"
)


# --------------------------------------------------
# VERİLERİ OKU
# --------------------------------------------------

nufus_verisi = pd.read_csv(
    nufus_veri_yolu
)
# --------------------------------------------------
# KAYNAK VERİDEKİ DOĞRULANMIŞ İLÇE KODU DÜZELTMESİ
# --------------------------------------------------

# İBB nüfus dosyasında Şile'nin ilçe kodu
# yanlışlıkla Sarıyer ile aynı, yani 1604 olarak
# bulunuyor.
#
# Resmî ilçe kodu listesine göre:
# Sarıyer = 1604
# Şile    = 1659

ilce_kodu_duzeltmeleri = {
    "Şile": 1659,
}


for ilce_adi, dogru_kod in ilce_kodu_duzeltmeleri.items():

    ilce_maskesi = (
        nufus_verisi["İlçe"]
        .astype(str)
        .str.strip()
        .eq(ilce_adi)
    )

    bulunan_kayit_sayisi = int(
        ilce_maskesi.sum()
    )

    if bulunan_kayit_sayisi != 1:
        raise ValueError(
            f"{ilce_adi} için tam olarak bir kayıt "
            f"bekleniyordu. Bulunan: "
            f"{bulunan_kayit_sayisi}"
        )

    eski_kod = int(
        nufus_verisi.loc[
            ilce_maskesi,
            "ilce_kodu",
        ].iloc[0]
    )

    nufus_verisi.loc[
        ilce_maskesi,
        "ilce_kodu",
    ] = dogru_kod

    print(
        f"İlçe kodu düzeltildi: "
        f"{ilce_adi} "
        f"{eski_kod} → {dogru_kod}"
    )


# Düzeltmeden sonra başka tekrar eden
# ilçe kodu kalıp kalmadığını kontrol et.
tekrar_eden_kodlar = nufus_verisi[
    nufus_verisi.duplicated(
        subset=["ilce_kodu"],
        keep=False,
    )
]

if not tekrar_eden_kodlar.empty:
    raise ValueError(
        "Düzeltmeden sonra tekrar eden ilçe "
        "kodları hâlâ bulunuyor:\n"
        + tekrar_eden_kodlar[
            [
                "İlçe",
                "ilce_kodu",
            ]
        ].to_string(index=False)
    )

ilce_geojson = json.loads(
    ilce_geojson_yolu.read_text(
        encoding="utf-8"
    )
)


# --------------------------------------------------
# VERİLERİ KONTROL ET
# --------------------------------------------------

gerekli_nufus_sutunlari = {
    "Yıl",
    "İlçe",
    "ilce_kodu",
    "Toplam Nüfus",
}

eksik_sutunlar = (
    gerekli_nufus_sutunlari
    - set(nufus_verisi.columns)
)

if eksik_sutunlar:
    raise ValueError(
        "Nüfus dosyasında eksik sütunlar var: "
        f"{sorted(eksik_sutunlar)}"
    )


# Yalnızca 2025 yılına ait kayıtlarla
# çalıştığımızı doğrula.
kullanilan_yillar = set(
    nufus_verisi["Yıl"]
    .dropna()
    .astype(int)
)

if kullanilan_yillar != {2025}:
    raise ValueError(
        "Nüfus dosyasında beklenmeyen yıllar var: "
        f"{sorted(kullanilan_yillar)}"
    )


# İstanbul'un 39 ilçesinin bulunmasını bekliyoruz.
if len(nufus_verisi) != 39:
    raise ValueError(
        "Nüfus dosyasında 39 ilçe bulunamadı. "
        f"Bulunan kayıt: {len(nufus_verisi)}"
    )


if len(ilce_geojson.get("features", [])) != 39:
    raise ValueError(
        "GeoJSON dosyasında 39 ilçe bulunamadı."
    )


# --------------------------------------------------
# GEOJSON İLÇE SÖZLÜĞÜ OLUŞTUR
# --------------------------------------------------

geojson_ilceleri = {}

for feature in ilce_geojson["features"]:

    ilce_adi = str(
        feature["properties"]["name"]
    ).strip()

    geojson_ilceleri[ilce_adi] = feature


# --------------------------------------------------
# İLÇE ADLARINI TEMİZLE
# --------------------------------------------------

nufus_verisi["İlçe"] = (
    nufus_verisi["İlçe"]
    .astype(str)
    .str.strip()
)


# Nüfus ve GeoJSON dosyalarındaki ilçe
# isimlerinin tam olarak eşleştiğini doğrula.
nufus_ilceleri = set(
    nufus_verisi["İlçe"]
)

geojson_ilce_adlari = set(
    geojson_ilceleri.keys()
)

if nufus_ilceleri != geojson_ilce_adlari:

    sadece_nufusta = sorted(
        nufus_ilceleri
        - geojson_ilce_adlari
    )

    sadece_geojsonda = sorted(
        geojson_ilce_adlari
        - nufus_ilceleri
    )

    raise ValueError(
        "İlçe adları eşleşmiyor.\n"
        f"Yalnızca nüfusta: {sadece_nufusta}\n"
        f"Yalnızca GeoJSON'da: {sadece_geojsonda}"
    )


# --------------------------------------------------
# VERİ TABANI BAĞLANTISI
# --------------------------------------------------

def veritabani_baglantisi_olustur():

    if not veritabani_yolu.exists():
        raise FileNotFoundError(
            "Veri tabanı bulunamadı. Önce "
            "veritabani_olustur.py dosyasını çalıştır."
        )

    baglanti = sqlite3.connect(
        veritabani_yolu
    )

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# --------------------------------------------------
# İLÇELERİ VERİ TABANINA AKTAR
# --------------------------------------------------

def ilceleri_aktar(baglanti):

    aktarilan_ilce_sayisi = 0

    for _, satir in nufus_verisi.iterrows():

        ilce_adi = str(
            satir["İlçe"]
        ).strip()

        ilce_kodu = int(
            satir["ilce_kodu"]
        )

        toplam_nufus = int(
            satir["Toplam Nüfus"]
        )


        # İlçenin GeoJSON kaydından yalnızca
        # geometri bölümünü alıyoruz.
        geometri = geojson_ilceleri[
            ilce_adi
        ]["geometry"]

        geometri_metni = json.dumps(
            geometri,
            ensure_ascii=False,
        )


        baglanti.execute(
            """
            INSERT INTO districts (
                name,
                district_code,
                population_2025,
                geometry_geojson,
                geometry_source
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(name)
            DO UPDATE SET
                district_code =
                    excluded.district_code,

                population_2025 =
                    excluded.population_2025,

                geometry_geojson =
                    excluded.geometry_geojson,

                geometry_source =
                    excluded.geometry_source;
            """,
            (
                ilce_adi,
                ilce_kodu,
                toplam_nufus,
                geometri_metni,
                (
                    "OpenStreetMap tabanlı açık "
                    "İstanbul ilçe sınırı GeoJSON verisi"
                ),
            ),
        )

        aktarilan_ilce_sayisi += 1

    return aktarilan_ilce_sayisi


# --------------------------------------------------
# KÜTÜPHANE HİZMET TÜRÜNÜ EKLE
# --------------------------------------------------

def kutuphane_hizmet_turunu_ekle(
    baglanti
):

    baglanti.execute(
        """
        INSERT INTO service_types (
            name,
            description,
            is_active
        )
        VALUES (?, ?, ?)

        ON CONFLICT(name)
        DO UPDATE SET
            description =
                excluded.description,

            is_active =
                excluded.is_active;
        """,
        (
            "Kütüphane",
            (
                "İBB kütüphane konumları ve "
                "ilçe bazlı hizmet erişilebilirliği"
            ),
            1,
        ),
    )


# --------------------------------------------------
# SONUÇLARI KONTROL ET
# --------------------------------------------------

def kayit_sayilarini_getir(
    baglanti
):

    ilce_sayisi = baglanti.execute(
        """
        SELECT COUNT(*)
        FROM districts;
        """
    ).fetchone()[0]

    hizmet_turu_sayisi = baglanti.execute(
        """
        SELECT COUNT(*)
        FROM service_types;
        """
    ).fetchone()[0]

    return (
        ilce_sayisi,
        hizmet_turu_sayisi,
    )


def ilk_bes_ilceyi_getir(
    baglanti
):

    return baglanti.execute(
        """
        SELECT
            id,
            name,
            district_code,
            population_2025

        FROM districts

        ORDER BY name

        LIMIT 5;
        """
    ).fetchall()


# --------------------------------------------------
# ANA ÇALIŞMA AKIŞI
# --------------------------------------------------

def main():

    with veritabani_baglantisi_olustur() as baglanti:

        aktarilan_ilce_sayisi = (
            ilceleri_aktar(
                baglanti
            )
        )

        kutuphane_hizmet_turunu_ekle(
            baglanti
        )


        # with bloğundan normal biçimde çıkıldığında
        # SQLite değişiklikleri kaydeder.
        ilce_sayisi, hizmet_turu_sayisi = (
            kayit_sayilarini_getir(
                baglanti
            )
        )

        ilk_bes_ilce = (
            ilk_bes_ilceyi_getir(
                baglanti
            )
        )


    print(
        f"İşlenen ilçe kaydı: "
        f"{aktarilan_ilce_sayisi}"
    )

    print(
        f"Veri tabanındaki ilçe sayısı: "
        f"{ilce_sayisi}"
    )

    print(
        f"Veri tabanındaki hizmet türü sayısı: "
        f"{hizmet_turu_sayisi}"
    )

    print(
        "\nVeri tabanındaki ilk 5 ilçe:"
    )

    for (
        ilce_id,
        ilce_adi,
        ilce_kodu,
        nufus,
    ) in ilk_bes_ilce:

        print(
            f"- ID={ilce_id} | "
            f"{ilce_adi} | "
            f"kod={ilce_kodu} | "
            f"nüfus={nufus:,}"
        )


if __name__ == "__main__":
    main()
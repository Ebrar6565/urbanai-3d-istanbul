from pathlib import Path
import sqlite3

import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

veritabani_yolu = Path(
    "data/database/urbanai.db"
)

kutuphane_veri_yolu = Path(
    "data/processed/ibb_kutuphaneleri_koordinatli.csv"
)


# --------------------------------------------------
# VERİYİ OKU
# --------------------------------------------------

kutuphane_verisi = pd.read_csv(
    kutuphane_veri_yolu
)


# --------------------------------------------------
# GEREKLİ SÜTUNLARI KONTROL ET
# --------------------------------------------------

gerekli_sutunlar = {
    "Kütüphane Adı",
    "İlçe Adı",
    "Açılış Yılı",
    "Adres",
    "Telefon",
    "Çalışma Saatleri",
    "Çalışma Günleri",
    "Çalışma Bilgisi Eksik",
    "Enlem",
    "Boylam",
    "Koordinat Sorgusu",
    "Bulunan Adres",
}

eksik_sutunlar = (
    gerekli_sutunlar
    - set(kutuphane_verisi.columns)
)

if eksik_sutunlar:
    raise ValueError(
        "Kütüphane dosyasında eksik sütunlar var: "
        f"{sorted(eksik_sutunlar)}"
    )


# Bu veri setinde 72 temiz kayıt bekliyoruz.
if len(kutuphane_verisi) != 72:
    raise ValueError(
        "Kütüphane dosyasında 72 kayıt bekleniyordu. "
        f"Bulunan kayıt: {len(kutuphane_verisi)}"
    )


# --------------------------------------------------
# TEMİZLEME YARDIMCI FONKSİYONLARI
# --------------------------------------------------

def metin_veya_none(deger):
    """
    Boş ve NaN değerleri None'a dönüştürür.

    SQLite tarafında Python'daki None değeri,
    SQL NULL olarak kaydedilir.
    """

    if pd.isna(deger):
        return None

    temiz_deger = str(deger).strip()

    if temiz_deger == "":
        return None

    return temiz_deger


def tam_sayi_veya_none(deger):
    """
    Açılış yılı gibi değerleri tam sayıya
    dönüştürür. Boşsa None döndürür.
    """

    if pd.isna(deger):
        return None

    try:
        return int(
            float(deger)
        )

    except (TypeError, ValueError):
        return None


def mantiksal_degeri_sayiya_cevir(deger):
    """
    True/False benzeri değerleri SQLite için
    1 veya 0 biçimine dönüştürür.
    """

    if pd.isna(deger):
        return 0

    if isinstance(deger, str):
        return int(
            deger.strip().lower()
            in {
                "true",
                "1",
                "evet",
                "yes",
            }
        )

    return int(
        bool(deger)
    )


# --------------------------------------------------
# İLÇE ADLARINI VE KOORDİNATLARI TEMİZLE
# --------------------------------------------------

kutuphane_verisi["İlçe Adı"] = (
    kutuphane_verisi["İlçe Adı"]
    .astype(str)
    .str.strip()
)

kutuphane_verisi["Kütüphane Adı"] = (
    kutuphane_verisi["Kütüphane Adı"]
    .astype(str)
    .str.strip()
)

kutuphane_verisi["Enlem"] = pd.to_numeric(
    kutuphane_verisi["Enlem"],
    errors="coerce",
)

kutuphane_verisi["Boylam"] = pd.to_numeric(
    kutuphane_verisi["Boylam"],
    errors="coerce",
)


# --------------------------------------------------
# KOORDİNAT KALİTE DURUMUNU BELİRLE
# --------------------------------------------------

koordinati_bulunan = (
    kutuphane_verisi["Enlem"].notna()
    & kutuphane_verisi["Boylam"].notna()
)

kutuphane_ifadesi = (
    r"kütüphane|kitaplık|kitaplığ|library"
)

adresi_guvenilir = (
    kutuphane_verisi["Bulunan Adres"]
    .fillna("")
    .astype(str)
    .str.contains(
        kutuphane_ifadesi,
        case=False,
        regex=True,
    )
)


# Başlangıçta bütün kayıtları eksik kabul ediyoruz.
kutuphane_verisi["coordinate_status"] = (
    "missing"
)


# Koordinatı ve güvenilir adres ifadesi bulunanlar.
kutuphane_verisi.loc[
    koordinati_bulunan
    & adresi_guvenilir,
    "coordinate_status",
] = "verified"


# Koordinatı var fakat bulunan adres şüpheli.
kutuphane_verisi.loc[
    koordinati_bulunan
    & ~adresi_guvenilir,
    "coordinate_status",
] = "suspicious"


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
# İLÇE KİMLİKLERİNİ GETİR
# --------------------------------------------------

def ilce_idlerini_getir(baglanti):

    sonuc = baglanti.execute(
        """
        SELECT
            name,
            id
        FROM districts;
        """
    ).fetchall()

    return {
        ilce_adi: ilce_id
        for ilce_adi, ilce_id in sonuc
    }


# --------------------------------------------------
# KÜTÜPHANE HİZMET TÜRÜ KİMLİĞİNİ GETİR
# --------------------------------------------------

def kutuphane_hizmet_turu_id_getir(
    baglanti
):

    sonuc = baglanti.execute(
        """
        SELECT id
        FROM service_types
        WHERE name = ?;
        """,
        (
            "Kütüphane",
        ),
    ).fetchone()

    if sonuc is None:
        raise ValueError(
            "Kütüphane hizmet türü bulunamadı. "
            "Önce veritabani_veri_aktar.py "
            "dosyasını çalıştır."
        )

    return sonuc[0]


# --------------------------------------------------
# KÜTÜPHANELERİ AKTAR
# --------------------------------------------------

def kutuphaneleri_aktar(
    baglanti,
    ilce_idleri,
    hizmet_turu_id,
):

    veri_ilceleri = set(
        kutuphane_verisi["İlçe Adı"]
    )

    veritabani_ilceleri = set(
        ilce_idleri.keys()
    )

    eslesmeyen_ilceler = sorted(
        veri_ilceleri
        - veritabani_ilceleri
    )

    if eslesmeyen_ilceler:
        raise ValueError(
            "Veri tabanında bulunmayan ilçeler var: "
            f"{eslesmeyen_ilceler}"
        )


    islenen_kayit_sayisi = 0

    for _, satir in kutuphane_verisi.iterrows():

        ilce_adi = satir[
            "İlçe Adı"
        ]

        ilce_id = ilce_idleri[
            ilce_adi
        ]

        kutuphane_adi = str(
            satir["Kütüphane Adı"]
        ).strip()

        # UNIQUE kontrolünün tekrar çalıştırmalarda
        # doğru işlemesi için boş adresi boş metin
        # olarak saklıyoruz.
        adres = (
            metin_veya_none(
                satir["Adres"]
            )
            or ""
        )

        enlem = (
            None
            if pd.isna(satir["Enlem"])
            else float(satir["Enlem"])
        )

        boylam = (
            None
            if pd.isna(satir["Boylam"])
            else float(satir["Boylam"])
        )


        baglanti.execute(
            """
            INSERT INTO facilities (
                service_type_id,
                district_id,
                name,
                opening_year,
                address,
                phone,
                working_hours,
                working_days,
                working_info_missing,
                latitude,
                longitude,
                coordinate_query,
                found_address,
                coordinate_status,
                source_name
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )

            ON CONFLICT(
                service_type_id,
                name,
                address
            )
            DO UPDATE SET
                district_id =
                    excluded.district_id,

                opening_year =
                    excluded.opening_year,

                phone =
                    excluded.phone,

                working_hours =
                    excluded.working_hours,

                working_days =
                    excluded.working_days,

                working_info_missing =
                    excluded.working_info_missing,

                latitude =
                    excluded.latitude,

                longitude =
                    excluded.longitude,

                coordinate_query =
                    excluded.coordinate_query,

                found_address =
                    excluded.found_address,

                coordinate_status =
                    excluded.coordinate_status,

                source_name =
                    excluded.source_name;
            """,
            (
                hizmet_turu_id,
                ilce_id,
                kutuphane_adi,

                tam_sayi_veya_none(
                    satir["Açılış Yılı"]
                ),

                adres,

                metin_veya_none(
                    satir["Telefon"]
                ),

                metin_veya_none(
                    satir["Çalışma Saatleri"]
                ),

                metin_veya_none(
                    satir["Çalışma Günleri"]
                ),

                mantiksal_degeri_sayiya_cevir(
                    satir[
                        "Çalışma Bilgisi Eksik"
                    ]
                ),

                enlem,
                boylam,

                metin_veya_none(
                    satir["Koordinat Sorgusu"]
                ),

                metin_veya_none(
                    satir["Bulunan Adres"]
                ),

                satir["coordinate_status"],

                (
                    "İBB Kütüphaneleri Lokasyon, "
                    "Çalışma Gün ve Saatleri"
                ),
            ),
        )

        islenen_kayit_sayisi += 1

    return islenen_kayit_sayisi


# --------------------------------------------------
# SONUÇLARI GETİR
# --------------------------------------------------

def sonuc_ozetini_getir(
    baglanti,
    hizmet_turu_id,
):

    toplam_kayit = baglanti.execute(
        """
        SELECT COUNT(*)
        FROM facilities
        WHERE service_type_id = ?;
        """,
        (
            hizmet_turu_id,
        ),
    ).fetchone()[0]


    durum_sayilari = baglanti.execute(
        """
        SELECT
            coordinate_status,
            COUNT(*)

        FROM facilities

        WHERE service_type_id = ?

        GROUP BY coordinate_status

        ORDER BY coordinate_status;
        """,
        (
            hizmet_turu_id,
        ),
    ).fetchall()


    ilk_bes_kayit = baglanti.execute(
        """
        SELECT
            facilities.id,
            facilities.name,
            districts.name,
            facilities.coordinate_status

        FROM facilities

        INNER JOIN districts
            ON districts.id =
               facilities.district_id

        WHERE facilities.service_type_id = ?

        ORDER BY facilities.id

        LIMIT 5;
        """,
        (
            hizmet_turu_id,
        ),
    ).fetchall()


    return (
        toplam_kayit,
        durum_sayilari,
        ilk_bes_kayit,
    )


# --------------------------------------------------
# ANA ÇALIŞMA AKIŞI
# --------------------------------------------------

def main():

    with veritabani_baglantisi_olustur() as baglanti:

        ilce_idleri = ilce_idlerini_getir(
            baglanti
        )

        hizmet_turu_id = (
            kutuphane_hizmet_turu_id_getir(
                baglanti
            )
        )

        islenen_kayit_sayisi = (
            kutuphaneleri_aktar(
                baglanti,
                ilce_idleri,
                hizmet_turu_id,
            )
        )

        (
            toplam_kayit,
            durum_sayilari,
            ilk_bes_kayit,
        ) = sonuc_ozetini_getir(
            baglanti,
            hizmet_turu_id,
        )


    print(
        f"İşlenen kütüphane kaydı: "
        f"{islenen_kayit_sayisi}"
    )

    print(
        f"Veri tabanındaki kütüphane sayısı: "
        f"{toplam_kayit}"
    )

    print(
        "\nKoordinat kalite durumları:"
    )

    for durum, sayi in durum_sayilari:
        print(
            f"- {durum}: {sayi}"
        )


    print(
        "\nVeri tabanındaki ilk 5 kütüphane:"
    )

    for (
        kayit_id,
        kutuphane_adi,
        ilce_adi,
        koordinat_durumu,
    ) in ilk_bes_kayit:

        print(
            f"- ID={kayit_id} | "
            f"{kutuphane_adi} | "
            f"{ilce_adi} | "
            f"{koordinat_durumu}"
        )


if __name__ == "__main__":
    main()
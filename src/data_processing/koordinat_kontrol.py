from pathlib import Path

import pandas as pd


veri_yolu = Path(
    "data/processed/ibb_kutuphaneleri_koordinatli.csv"
)

rapor_yolu = Path(
    "data/processed/koordinat_kontrol_listesi.csv"
)


veri = pd.read_csv(veri_yolu)


# Enlem veya boylam değeri eksik olan kayıtlar
eksik_koordinat = veri[
    ["Enlem", "Boylam"]
].isna().any(axis=1)


# Nominatim tarafından döndürülen adres
bulunan_adres = veri["Bulunan Adres"].fillna("").astype(str)


# Dönen adresin gerçekten bir kütüphane veya kitaplık
# kaydı içerip içermediğini kontrol et
kutuphane_ifadesi_var = bulunan_adres.str.contains(
    r"kütüphane|kitaplık|kitaplığ|library",
    case=False,
    regex=True,
)

# Koordinatı var fakat bulunan adres kütüphaneye benzemiyor
supheli_eslesme = (
    ~eksik_koordinat
    & ~kutuphane_ifadesi_var
)


veri["Koordinat Kontrol Durumu"] = "Otomatik eşleşme"

veri.loc[
    eksik_koordinat,
    "Koordinat Kontrol Durumu",
] = "Koordinat bulunamadı"

veri.loc[
    supheli_eslesme,
    "Koordinat Kontrol Durumu",
] = "Elle kontrol gerekli"


kontrol_listesi = veri[
    veri["Koordinat Kontrol Durumu"] != "Otomatik eşleşme"
][
    [
        "Kütüphane Adı",
        "İlçe Adı",
        "Adres",
        "Enlem",
        "Boylam",
        "Bulunan Adres",
        "Koordinat Kontrol Durumu",
    ]
]


kontrol_listesi.to_csv(
    rapor_yolu,
    index=False,
    encoding="utf-8-sig",
)


print("Koordinat kalite kontrolü tamamlandı.")

print(
    f"Koordinat bulunamayan kayıt: "
    f"{eksik_koordinat.sum()}"
)

print(
    f"Şüpheli eşleşme: "
    f"{supheli_eslesme.sum()}"
)


print("\n=== KOORDİNATI BULUNAMAYANLAR ===")

print(
    veri.loc[
        eksik_koordinat,
        ["Kütüphane Adı", "İlçe Adı"],
    ].to_string(index=False)
)


print("\n=== ELLE KONTROL EDİLMESİ GEREKENLER ===")

print(
    veri.loc[
        supheli_eslesme,
        [
            "Kütüphane Adı",
            "İlçe Adı",
            "Bulunan Adres",
        ],
    ].to_string(index=False)
)


print(f"\nKontrol dosyası: {rapor_yolu}")
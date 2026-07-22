from pathlib import Path
import sqlite3


# --------------------------------------------------
# VERİ TABANI DOSYA YOLU
# --------------------------------------------------

veritabani_yolu = Path(
    "data/database/urbanai.db"
)


# --------------------------------------------------
# VERİ TABANI ŞEMASI
# --------------------------------------------------

veritabani_semasi = """
PRAGMA foreign_keys = ON;


-- İlçe bilgileri
CREATE TABLE IF NOT EXISTS districts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL UNIQUE,

    district_code INTEGER UNIQUE,

    population_2025 INTEGER
        CHECK (
            population_2025 IS NULL
            OR population_2025 >= 0
        ),

    geometry_geojson TEXT,

    geometry_source TEXT,

    created_at TEXT
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);


-- Hizmet türleri
CREATE TABLE IF NOT EXISTS service_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL UNIQUE,

    description TEXT,

    is_active INTEGER
        NOT NULL
        DEFAULT 1
        CHECK (
            is_active IN (0, 1)
        ),

    created_at TEXT
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);


-- Kütüphane, park, spor tesisi gibi hizmet noktaları
CREATE TABLE IF NOT EXISTS facilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    service_type_id INTEGER NOT NULL,

    district_id INTEGER NOT NULL,

    name TEXT NOT NULL,

    opening_year INTEGER,

    address TEXT,

    phone TEXT,

    working_hours TEXT,

    working_days TEXT,

    working_info_missing INTEGER
        NOT NULL
        DEFAULT 0
        CHECK (
            working_info_missing IN (0, 1)
        ),

    latitude REAL,

    longitude REAL,

    coordinate_query TEXT,

    found_address TEXT,

    coordinate_status TEXT
        NOT NULL
        DEFAULT 'unchecked'
        CHECK (
            coordinate_status IN (
                'verified',
                'suspicious',
                'missing',
                'unchecked'
            )
        ),

    source_name TEXT,

    created_at TEXT
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (service_type_id)
        REFERENCES service_types(id),

    FOREIGN KEY (district_id)
        REFERENCES districts(id),

    UNIQUE (
        service_type_id,
        name,
        address
    )
);


-- İlçe bazlı hizmet analiz sonuçları
CREATE TABLE IF NOT EXISTS district_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    district_id INTEGER NOT NULL,

    service_type_id INTEGER NOT NULL,

    analysis_year INTEGER NOT NULL,

    population INTEGER
        CHECK (
            population IS NULL
            OR population >= 0
        ),

    facility_count INTEGER
        NOT NULL
        DEFAULT 0
        CHECK (
            facility_count >= 0
        ),

    service_per_100k REAL,

    people_per_facility INTEGER,

    population_score REAL,

    service_gap_score REAL,

    priority_score REAL,

    priority_level TEXT,

    data_status TEXT,

    priority_rank INTEGER,

    created_at TEXT
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (district_id)
        REFERENCES districts(id),

    FOREIGN KEY (service_type_id)
        REFERENCES service_types(id),

    UNIQUE (
        district_id,
        service_type_id,
        analysis_year
    )
);


-- Sorguların daha hızlı çalışması için indeksler
CREATE INDEX IF NOT EXISTS
    idx_facilities_district
ON facilities(district_id);


CREATE INDEX IF NOT EXISTS
    idx_facilities_service_type
ON facilities(service_type_id);


CREATE INDEX IF NOT EXISTS
    idx_district_metrics_district
ON district_metrics(district_id);


CREATE INDEX IF NOT EXISTS
    idx_district_metrics_service_type
ON district_metrics(service_type_id);
"""


# --------------------------------------------------
# VERİ TABANI BAĞLANTISI
# --------------------------------------------------

def veritabani_baglantisi_olustur():
    """
    SQLite veri tabanına bağlantı oluşturur.

    Dosya henüz yoksa SQLite tarafından
    otomatik olarak oluşturulur.
    """

    veritabani_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    baglanti = sqlite3.connect(
        veritabani_yolu
    )

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# --------------------------------------------------
# TABLOLARI OLUŞTUR
# --------------------------------------------------

def tablolari_olustur():
    """
    SQL şemasındaki tabloları ve indeksleri oluşturur.
    """

    with veritabani_baglantisi_olustur() as baglanti:
        baglanti.executescript(
            veritabani_semasi
        )


# --------------------------------------------------
# TABLOLARI LİSTELE
# --------------------------------------------------

def tablolari_listele():
    """
    Veri tabanındaki uygulama tablolarını listeler.
    """

    with veritabani_baglantisi_olustur() as baglanti:

        sonuc = baglanti.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
            """
        ).fetchall()

    return [
        satir[0]
        for satir in sonuc
    ]


# --------------------------------------------------
# ANA ÇALIŞMA AKIŞI
# --------------------------------------------------

def main():

    tablolari_olustur()

    tablolar = tablolari_listele()

    print(
        f"Veri tabanı oluşturuldu: "
        f"{veritabani_yolu}"
    )

    print(
        f"Toplam uygulama tablosu: "
        f"{len(tablolar)}"
    )

    print(
        "\nOluşturulan tablolar:"
    )

    for tablo in tablolar:
        print(
            f"- {tablo}"
        )


if __name__ == "__main__":
    main()
# DESIGN_FINAL.md
# UrbanAI 3D İstanbul — Approved Visual Design System

**Source screen:** "Aday Bölgeler — Esenyurt Mekânsal Karar Destek"
**Project:** Spatial Decision Support System (`projects/14826075538386410616`)
**Screen ID:** `projects/14826075538386410616/screens/8ff39de657ce45919d5d1ecaaa00118a`
**Extracted from:** Stitch-generated HTML (visual reference only — not geographic ground truth)
**Last corrected:** 2026-07-24 — aligned with real FastAPI endpoints, nested field paths, and scientific rules

---

> **Factual rules — must be enforced throughout the entire application**
>
> - All candidate data comes from the real FastAPI API (see §0).
> - Candidate array is at `response.aday_bolgeler` — never treat the response root as the array.
> - Satellite array is at `response.uydu_goruntuleri`.
> - The two scoring axes **must remain permanently separate and must never be combined**:
>   1. **`candidate.hizmet_ihtiyaci.puan`** — service-need score → encoded as **polygon fill colour**
>   2. **`candidate.yer_inceleme.durum`** — site-review status → encoded as **polygon border colour**
> - Do not copy invented cell IDs, scores, distances, dates or parcel numbers from the Stitch mock.
> - Do not create a "combined suitability score."
> - Do not invent any values not returned by the API.
> - Do not hard-code the district list — derive it dynamically from the API.
> - Do not include profile sections, user accounts, notifications, messaging or role labels.
> - Do not include report-generation, GeoTIFF download or approval buttons.

---

## 0. Real API Endpoints and Response Envelopes

All data displayed in the interface must come exclusively from these endpoints.

| Endpoint | Purpose |
|---|---|
| `GET /api/aday-bolgeler` | All candidate cells (all districts) |
| `GET /api/aday-bolgeler?ilce={ilce}` | Candidate cells filtered by district |
| `GET /api/aday-bolgeler?ilce={ilce}&geometri=true` | Candidate cells + GeoJSON geometries for map rendering |
| `GET /api/aday-bolgeler/{hucre_id}` | Single candidate cell detail (always includes geometry) |
| `GET /api/ilceler` | All 39 districts — use only for non-candidate-specific selectors |
| `GET /api/uydu-goruntuleri?ilce={ilce}` | Satellite patches for a district |

Do not use `/api/candidates` or `/api/districts` — these endpoints do not exist.

### List response envelope — `/api/aday-bolgeler`

```json
{
  "filtreler": { "ilce": "...", "analiz_yili": null, "worldcover_yili": null, "limit": 50, "geometri": false },
  "toplam_kayit": 42,
  "aday_bolgeler": [ ...candidate objects... ]
}
```

The candidate array is at **`response.aday_bolgeler`**. Do not treat the response root as the array.

### Single-record response — `/api/aday-bolgeler/{hucre_id}`

Returns a single candidate object directly (no envelope). Geometry is always included.

### Geometry field name — confirmed from source

When `geometri=true` is passed, each candidate object contains:

```json
{ "geometri": { ...GeoJSON Polygon or MultiPolygon... } }
```

The field is named **`geometri`** (Turkish spelling). Do not use `geometry`, `geojson`, or `feature`.

### Satellite response envelope — `/api/uydu-goruntuleri?ilce={ilce}`

```json
{
  "uydu_goruntuleri": [ ...patch objects... ]
}
```

The satellite patch array is at **`response.uydu_goruntuleri`**.

### Candidate object — full nested field schema

Confirmed from `src/api/aday_bolgeler.py`:

```
candidate.hucre_id                                  — cell identifier
candidate.ilce                                      — district name
candidate.analiz_yili                               — analysis year
candidate.worldcover_yili                           — WorldCover data year

candidate.hizmet_ihtiyaci.sira                      — service-need rank
candidate.hizmet_ihtiyaci.puan                      — service-need score  ← FILL AXIS
candidate.hizmet_ihtiyaci.seviye                    — service-need level label

candidate.en_yakin_kutuphane.ad                     — nearest library name
candidate.en_yakin_kutuphane.uzaklik_km             — distance to nearest library (km)

candidate.arazi_ortusu.yapilasmis_alan_yuzde        — built-up area %
candidate.arazi_ortusu.bitkisel_yesil_alan_yuzde    — vegetation / green area %
candidate.arazi_ortusu.acik_ciplak_alan_yuzde       — open / bare area %
candidate.arazi_ortusu.su_sulak_alan_yuzde          — water / wetland area %
candidate.arazi_ortusu.worldcover_kapsama_yuzde     — WorldCover coverage %

candidate.yer_inceleme.durum                        — site-review status  ← BORDER AXIS
candidate.yer_inceleme.aciklama                     — site-review explanation

candidate.genel_degerlendirme                       — general evaluation text
candidate.merkez.enlem                              — centroid latitude
candidate.merkez.boylam                             — centroid longitude
candidate.geometri                                  — GeoJSON geometry (only when geometri=true)
```

### Satellite patch object — field schema

```
patch.hucre_id          — cell identifier (match against candidate.hucre_id)
patch.gorsel.goruntu_url — URL of the RGB preview image
```

---

## 1. Overall Layout — 1440 px Desktop Canvas

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  SIDEBAR 216px  │           TOP BAR 60px (right of sidebar)                     │
├─────────────────┼──────────────────────────────────────────────────────────────┤
│                 │  CANDIDATE LIST  │        MAP WORKSPACE        │ DETAIL PANEL │
│   SIDEBAR       │     250px        │       (flex-1, fluid)       │   340px      │
│   216px         │                  │                             │              │
│   (fixed)       │  (fixed width)   │  >= 55 % of visible area   │ (fixed width)│
│                 │                  │                             │              │
└─────────────────┴──────────────────┴─────────────────────────────┴──────────────┘
```

| Zone | CSS value | Notes |
|---|---|---|
| Sidebar width | `216px` | `w-[216px]`, fixed left, full-height |
| Top bar height | `60px` | `h-[60px]`, fixed top, spans right of sidebar |
| Candidate list width | `250px` | `w-[250px]`, left of map |
| Map workspace | `flex-1` | All remaining horizontal space |
| Detail panel width | `340px` | `w-[340px]`, right of map |
| Page margin | `24px` | `margin-page` token |
| Gutter (internal spacing) | `16px` | `gutter` token |

Main workspace: `position: fixed; top: 60px; left: 216px; right: 0; bottom: 0; display: flex`.

---

## 2. Sidebar — Navigation

### Structure

No profile block, no avatar, no user name, no role label, no notification centre.

```
Sidebar (216px wide, full height, fixed)
├── Brand block  (px-6 py-8)
│   ├── "UrbanAI 3D"                    — page-title, semibold, text-on-primary
│   └── "Kentsel Karar Destek Platformu" — 10px, uppercase, tracking-widest,
│                                          label-mono, opacity-80
└── Nav items  (flex-1, px-3, space-y-1)
    ├── Genel Bakış       icon: dashboard
    ├── İlçe Analizi      icon: location_city
    ├── Kütüphaneler      icon: menu_book
    ├── Aday Bölgeler     icon: location_on      <- ACTIVE STATE
    ├── Uydu Görüntüleri  icon: satellite_alt
    └── Metodoloji        icon: science
```

The sidebar has **no bottom profile block**. After the last nav item the sidebar simply ends.

### Nav item — inactive

```css
display: flex; align-items: center; gap: 12px;
padding: 10px 12px;                   /* px-3 py-2.5 */
color: #e4e2e4;                       /* text-surface-variant */
border-radius: 4px;
transition: background-color 150ms;
/* hover: */ background-color: #374860;  /* on-primary-fixed-variant */
```

Icon size: `20px` (Material Symbols Outlined)
Label: IBM Plex Sans 14px / 20px, weight 400

### Nav item — active ("Aday Bölgeler")

```css
position: relative; overflow: hidden;
background-color: #256489;          /* secondary */
color: #ffffff;
border-radius: 4px;
font-weight: 500;
/* Left indicator strip (4px): */
::before {
  position: absolute; left: 0; top: 0; bottom: 0;
  width: 4px; background-color: #95cdf7;  /* secondary-fixed-dim */
}
```

### Sidebar background

```css
background-color: #000b1c;             /* primary */
border-right: 1px solid #CBD2D8;       /* border-gray */
```

---

## 3. Top Bar

```css
height: 60px; position: fixed; left: 216px; right: 0; top: 0;
background: #fbf9fb;            /* surface */
border-bottom: 1px solid #CBD2D8;
padding: 0 16px;                /* gutter */
display: flex; justify-content: space-between; align-items: center;
z-index: 40;
```

**Left side:**
- `<h1>` "UrbanAI 3D İstanbul" — IBM Plex Sans 18px / 24px semibold, `color: #000b1c`

**Right side (left → right):**

| Element | Specification |
|---|---|
| District selector | `<select>` or custom dropdown; values derived from unique `candidate.ilce` values in `response.aday_bolgeler` (see §0 — district selector rule); width ~160px; border `1px solid #CBD2D8`; border-radius 8px; font-size 13px |
| Cell-ID search | width 256px; background `#f5f3f5`; border `1px solid #CBD2D8`; border-radius 8px; font-size 13px; left icon `search` 18px; placeholder "Hücre ID ara…" |
| Methodology / help link | text link or icon button; icon `help`; color `#44474d` |

**Do not include:** notifications button, settings button, profile button, user name, role label, or any invented dates.

If `candidate.analiz_yili` or `candidate.worldcover_yili` are returned by the API, they may be shown as compact read-only labels. Do not show invented dates.

---

## 4. Candidate List Panel

```css
width: 250px;
background: #fbf9fb;              /* surface */
border-right: 1px solid #CBD2D8;
display: flex; flex-direction: column;
```

### Panel header

```css
padding: 16px;
border-bottom: 1px solid #CBD2D8;
display: flex; justify-content: space-between; align-items: center;
```

- Label "ADAY BÖLGELER": IBM Plex Sans 14px, weight 600, `color: #000b1c`, uppercase, `letter-spacing: wider`
- Count badge — value from `response.toplam_kayit`: `background: #e4e2e4; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: JetBrains Mono`

### Candidate row — content fields

Each row must show only fields from `response.aday_bolgeler` (items of that array):

| UI label | API field path | Position |
|---|---|---|
| Rank | `candidate.hizmet_ihtiyaci.sira` | Left, top |
| Cell ID | `candidate.hucre_id` | Left, below rank |
| Score | `candidate.hizmet_ihtiyaci.puan` | Right, top |
| Level | `candidate.hizmet_ihtiyaci.seviye` | Right, below score |
| Review status (short) | `candidate.yer_inceleme.durum` | Right or below level |

**Do not show sub-location / neighbourhood / parcel name** — the API does not guarantee this field.

### Candidate row — unselected

```css
display: flex; align-items: center; gap: 12px;
padding: 16px;
border-bottom: 1px solid #CBD2D8;
cursor: pointer;
/* hover: */ background-color: #f5f3f5;
transition: background-color 150ms;
```

Left column (`flex-direction: column`):
- Rank (`candidate.hizmet_ihtiyaci.sira`): `font-family: JetBrains Mono; font-size: 11px; color: #44474d; text-transform: uppercase`
- Cell ID (`candidate.hucre_id`): `font-family: JetBrains Mono; font-size: 14px; color: #1b1b1d`

Right column (`ml-auto; align-items: flex-end`):
- Score (`candidate.hizmet_ihtiyaci.puan`): `font-size: 14px; font-weight: 600; color: #1b1b1d`
- Level (`candidate.hizmet_ihtiyaci.seviye`): `font-size: 10px; color: #44474d` (plain text)

### Candidate row — selected

```css
background-color: #c9e6ff;       /* secondary-fixed */
color: #001e2f;                  /* on-secondary-fixed */
border-left: 4px solid #256489;  /* secondary */
```

Selected score: `font-weight: 700`
Selected level badge: `background: #9ad3fd; padding: 2px 4px; border-radius: 2px; font-size: 10px`

---

## 5. Map Workspace

```css
flex: 1;
position: relative;
background-color: #efedef;   /* surface-container — shown while tiles load */
```

The map must occupy **at least 55 %** of the visible workspace area.

### District label overlay (top-left)

```css
position: absolute; top: 16px; left: 16px; z-index: 10;
background: rgba(251,249,251,0.9);
backdrop-filter: blur(8px);
border: 1px solid #CBD2D8;
padding: 8px 16px; border-radius: 8px;
box-shadow: 0 4px 6px rgba(0,0,0,0.07);
font-size: 18px; font-weight: 700; color: #000b1c;
text-transform: uppercase; letter-spacing: 0.15em;
```

Text content: district name from `GET /api/ilceler` (currently selected district). Do not hardcode.

### Candidate polygon encoding — TWO INDEPENDENT AXES

These axes must **never be combined**.

#### AXIS 1 — Fill colour: `candidate.hizmet_ihtiyaci.puan`

| Score range | Fill hex | Level label |
|---|---|---|
| 97 – 100 | `#1E3A8A` | En yüksek |
| 92 – 96.99 | `#1D4ED8` | Çok yüksek |
| 87 – 91.99 | `#3B82F6` | Yüksek |
| 82 – 86.99 | `#60A5FA` | Orta-yüksek |
| < 82 | `#BFDBFE` | Düşük |

Fill opacity:
- Unselected: `0.45`
- Selected: `0.75`

#### AXIS 2 — Border colour: `candidate.yer_inceleme.durum`

| `candidate.yer_inceleme.durum` value | Border hex |
|---|---|
| Ön saha ve parsel incelemesine öncelikli | `#15803D` |
| İkinci düzey saha incelemesi | `#D97706` |
| Yeşil alan niteliği araştırılmalı | `#7E22CE` |
| Yer bulunabilirliği sınırlı olabilir | `#DC2626` |
| Çevresel kısıt kontrolü gerekli | `#0891B2` |
| Ek verilerle değerlendirilmelidir | `#475569` |

Border width:
- Unselected: `1.5px`, stroke-dasharray `4,2`
- Selected: `3.5px`, solid

**Selection state must NOT replace the site-review border colour.** When a polygon is selected:
- preserve its site-review border colour (from AXIS 2)
- increase border width to `3.5px` solid
- increase fill opacity to `0.75`
- optionally add a neutral outer ring or drop-shadow to indicate selection

### Map controls (top-right)

```css
position: absolute; right: 16px; top: 16px; z-index: 10;
display: flex; flex-direction: column; gap: 8px;
```

Zoom cluster:
```css
background: #fbf9fb; border: 1px solid #CBD2D8; border-radius: 8px;
/* + button */ padding: 8px; hover: background #f5f3f5; border-radius: 4px;
/* divider  */ height: 1px; background: #CBD2D8; margin: 0 4px;
/* - button */ same as + button;
```

Layers button: `background: #fbf9fb; border: 1px solid #CBD2D8; padding: 8px; border-radius: 8px; icon: layers`
Locate button: same styles, `icon: my_location`

All map control icons: 24px Material Symbols Outlined

### Map legends — TWO SEPARATE PANELS

The two legends must never be merged.

#### Legend A — Dolgu: Hizmet İhtiyacı (bottom-left)

```css
position: absolute; left: 16px; bottom: 16px; z-index: 10;
background: rgba(251,249,251,0.95);
backdrop-filter: blur(8px);
border: 1px solid #CBD2D8;
border-radius: 8px; padding: 16px;
display: flex; flex-direction: column; gap: 12px;
width: 200px;
box-shadow: 0 4px 6px rgba(0,0,0,0.07);
```

Header: "DOLGU — HİZMET İHTİYACI", 12px, weight 700, uppercase, `color: #44474d`

| Swatch (16×16px, no radius) | Range | Label |
|---|---|---|
| `#1E3A8A` | 97–100 | En yüksek |
| `#1D4ED8` | 92–96.99 | Çok yüksek |
| `#3B82F6` | 87–91.99 | Yüksek |
| `#60A5FA` | 82–86.99 | Orta-yüksek |
| `#BFDBFE` | < 82 | Düşük |

#### Legend B — Sınır: Yer İnceleme Durumu (bottom-left, above Legend A or stacked)

Same container style as Legend A.

Header: "SINIR — YER İNCELEME DURUMU", same typographic style.

| Swatch (16px wide line, 2px tall) | Status label |
|---|---|
| `#15803D` | Ön saha ve parsel incelemesine öncelikli |
| `#D97706` | İkinci düzey saha incelemesi |
| `#7E22CE` | Yeşil alan niteliği araştırılmalı |
| `#DC2626` | Yer bulunabilirliği sınırlı olabilir |
| `#0891B2` | Çevresel kısıt kontrolü gerekli |
| `#475569` | Ek verilerle değerlendirilmelidir |

Swatch for border legend: a short horizontal line (16px wide, 2px tall) in the corresponding colour, no fill swatch.

---

## 6. Detail Panel

```css
width: 340px;
background: #fbf9fb;
border-left: 1px solid #CBD2D8;
display: flex; flex-direction: column;
overflow-y: auto;
```

### Section 1 — Identification (p-6, border-b)

**Cell ID line:**
```css
font-family: JetBrains Mono; font-size: 16px; font-weight: 700; color: #000b1c;
```
Format: `Hücre Kimliği: {candidate.hucre_id}`

**Hizmet ihtiyacı fields** (3 lines, `font-size: 14px; color: #1b1b1d`):

| UI label | API field path |
|---|---|
| `Hizmet ihtiyacı sırası:` | `candidate.hizmet_ihtiyaci.sira` |
| `Hizmet ihtiyacı puanı:` | `candidate.hizmet_ihtiyaci.puan` (one decimal) |
| `Hizmet ihtiyacı seviyesi:` | `candidate.hizmet_ihtiyaci.seviye` |

**Library info card** (when returned by API):
```css
background: #f5f3f5; border: 1px solid #CBD2D8; border-radius: 8px; padding: 16px;
font-size: 14px;
```

| UI label | API field path |
|---|---|
| `En yakın kütüphane:` | `candidate.en_yakin_kutuphane.ad` |
| `Kütüphaneye uzaklık:` | `candidate.en_yakin_kutuphane.uzaklik_km` (km, one decimal) |

Omit this card entirely if `candidate.en_yakin_kutuphane.ad` is null or absent.

### Section 2 — İnceleme Durumu (AXIS 2 — border axis)

Section heading: IBM Plex Sans 14px, weight 700, uppercase, `letter-spacing: wider; color: #44474d; margin-bottom: 12px`

Status card:
```css
background: rgba(154,211,253,0.15);
border: 1px solid rgba(37,100,137,0.2);
border-radius: 8px; padding: 12px;
display: flex; align-items: flex-start; gap: 12px;
```
Icon: `assignment_late`, FILL=1, 24px. Icon colour comes from the AXIS 2 border-colour table (§5), keyed on `candidate.yer_inceleme.durum`.
Text: `font-size: 14px; font-weight: 500; line-height: 1.4`

| UI label | API field path |
|---|---|
| Status line | `candidate.yer_inceleme.durum` |
| Explanation (second line, optional) | `candidate.yer_inceleme.aciklama` |

Do **not** invent or paraphrase either field.

If `candidate.genel_degerlendirme` is non-null, it may be shown below the explanation in a secondary text style (IBM Plex Sans 13px / `#44474d`).

Horizontal divider: `height: 1px; background: rgba(203,210,216,0.3);`

### Section 3 — Arazi Örtüsü (WorldCover)

Section heading: same style as §2 heading.

Year label — only when returned by API:

| UI label | API field path |
|---|---|
| `Yıl:` | `candidate.worldcover_yili` |
| `Kapsam:` | `candidate.arazi_ortusu.worldcover_kapsama_yuzde` (%) |

Four horizontal progress bars (`space-y-4`):

| Bar label | API field path | Fill colour | Fill hex |
|---|---|---|---|
| Yapılaşmış alan | `candidate.arazi_ortusu.yapilasmis_alan_yuzde` | `deep-slate` | `#26384A` |
| Bitkisel / yeşil alan | `candidate.arazi_ortusu.bitkisel_yesil_alan_yuzde` | `verified-green` | `#3E7C59` |
| Açık / çıplak alan | `candidate.arazi_ortusu.acik_ciplak_alan_yuzde` | `review-amber` | `#B77932` |
| Su / sulak alan | `candidate.arazi_ortusu.su_sulak_alan_yuzde` | `secondary` | `#256489` |

Each bar:
```css
/* Label row */
display: flex; justify-content: space-between;
font-family: JetBrains Mono; font-size: 14px; color: #1b1b1d;

/* Track */
width: 100%; height: 8px; background: #e4e2e4;
border-radius: 9999px; overflow: hidden;

/* Fill */
height: 100%; background: <colour>; width: <api_pct>%;
```

Footer metadata row (only when API returns values):
```css
margin-top: 16px; display: flex; gap: 16px;
font-family: JetBrains Mono; font-size: 12px; color: #44474d;
```
Labels: `Kapsam: %{candidate.arazi_ortusu.worldcover_kapsama_yuzde}` · `Yıl: {candidate.worldcover_yili}`

### Section 4 — Sentinel-2 RGB Preview (optional)

Section heading: same typographic style, `margin-bottom: 12px`

**Lookup logic:**
1. Call `GET /api/uydu-goruntuleri?ilce={candidate.ilce}`
2. Iterate `response.uydu_goruntuleri`
3. Find the patch where `patch.hucre_id === candidate.hucre_id`
4. If match found → display `patch.gorsel.goruntu_url` in the image frame below
5. If no match → show the placeholder text instead of the frame

**Image frame (when patch found):**
```css
position: relative;
width: 159px; height: 159px;
border: 1px solid #CBD2D8;
border-radius: 4px;
overflow: hidden;
```
- `<img src="{patch.gorsel.goruntu_url}">` fills frame via `object-cover`
- Bottom-right badge: `background: rgba(0,11,28,0.8); color: #fff; padding: 2px 4px; border-radius: 2px; font-family: JetBrains Mono; font-size: 10px` — content: `RGB 4-3-2`

**Placeholder (when no patch found):**
```css
font-size: 13px; color: #44474d; font-style: italic; padding: 8px 0;
```
Text: `"Bu aday bölge için uydu önizlemesi bulunamadı."`

Do **not** fabricate an image URL.

### Section 5 — Neutral Action (optional)

If the interface supports a drill-down view that opens data already returned by `GET /api/aday-bolgeler/{hucre_id}`, a single neutral action link or button may be shown:

```css
width: 100%; padding: 12px 16px;
background: transparent;
border: 1px solid #CBD2D8;
color: #000b1c;
font-size: 14px; font-weight: 500;
border-radius: 8px;
/* hover: */ background: #f5f3f5; transition: background 150ms;
```
Label: `Aday ayrıntılarını görüntüle`

**Do not include:** "DETAYLI ANALİZ RAPORU", report download, approval, GeoTIFF export, or any action not backed by the API.

---

## 7. Colour Tokens

### Core surface palette

| Token | Hex | Usage |
|---|---|---|
| `surface` | `#fbf9fb` | Panel backgrounds, top bar, detail panel |
| `surface-bright` | `#fbf9fb` | Same as surface |
| `surface-dim` | `#dbd9dc` | Dimmed surfaces |
| `surface-container` | `#efedef` | Map workspace background |
| `surface-container-low` | `#f5f3f5` | Hover background, library card |
| `surface-container-high` | `#e9e7ea` | — |
| `surface-container-highest` | `#e4e2e4` | Progress bar tracks, count badge |
| `surface-container-lowest` | `#ffffff` | Pure white |
| `surface-variant` | `#e4e2e4` | Inactive nav text |
| `background` | `#fbf9fb` | Document background |
| `workspace-gray` | `#ECEFF1` | Body background (behind layout) |

### Primary palette

| Token | Hex | Usage |
|---|---|---|
| `primary` | `#000b1c` | Sidebar bg, headings |
| `on-primary` | `#ffffff` | Text on primary |
| `primary-container` | `#102238` | Dark sidebar variant |
| `on-primary-container` | `#798aa4` | Muted text on primary |
| `primary-fixed` | `#d3e3ff` | Light tint |
| `primary-fixed-dim` | `#b6c8e4` | — |
| `on-primary-fixed` | `#091c32` | — |
| `on-primary-fixed-variant` | `#374860` | Nav hover background |
| `inverse-primary` | `#b6c8e4` | — |

### Secondary palette

| Token | Hex | Usage |
|---|---|---|
| `secondary` | `#256489` | Active nav bg, Su/sulak bar, status accent |
| `on-secondary` | `#ffffff` | Text on secondary |
| `secondary-container` | `#9ad3fd` | Selected level badge bg |
| `on-secondary-container` | `#195b80` | — |
| `secondary-fixed` | `#c9e6ff` | Selected row background |
| `secondary-fixed-dim` | `#95cdf7` | Active nav left-indicator strip |
| `on-secondary-fixed` | `#001e2f` | Text on selected row |
| `on-secondary-fixed-variant` | `#004c6e` | — |

### Text colours

| Token | Hex | Usage |
|---|---|---|
| `on-surface` | `#1b1b1d` | Primary body text |
| `on-surface-variant` | `#44474d` | Secondary / muted text, section headings |
| `on-background` | `#1b1b1d` | Document text |
| `outline` | `#74777d` | Subtle borders |
| `outline-variant` | `#c4c6cd` | Subtle dividers |

### Border

| Token | Hex |
|---|---|
| `border-gray` | `#CBD2D8` |

### Functional / semantic (AXIS 1 — fill: Hizmet ihtiyacı)

| Score range | Hex | Level label |
|---|---|---|
| 97–100 | `#1E3A8A` | En yüksek |
| 92–96.99 | `#1D4ED8` | Çok yüksek |
| 87–91.99 | `#3B82F6` | Yüksek |
| 82–86.99 | `#60A5FA` | Orta-yüksek |
| < 82 | `#BFDBFE` | Düşük |

### Functional / semantic (AXIS 2 — border: Yer inceleme durumu)

| Status | Hex |
|---|---|
| Ön saha ve parsel incelemesine öncelikli | `#15803D` |
| İkinci düzey saha incelemesi | `#D97706` |
| Yeşil alan niteliği araştırılmalı | `#7E22CE` |
| Yer bulunabilirliği sınırlı olabilir | `#DC2626` |
| Çevresel kısıt kontrolü gerekli | `#0891B2` |
| Ek verilerle değerlendirilmelidir | `#475569` |

### Land-cover bar colours

| Bar | Token | Hex |
|---|---|---|
| Yapılaşmış alan | `deep-slate` | `#26384A` |
| Bitkisel / yeşil alan | `verified-green` | `#3E7C59` |
| Açık / çıplak alan | `review-amber` | `#B77932` |
| Su / sulak alan | `secondary` | `#256489` |

---

## 8. Typography

| Token name | Font family | Size | Line height | Weight |
|---|---|---|---|---|
| `page-title` | IBM Plex Sans | 28px | 36px | 600 |
| `section-title` | IBM Plex Sans | 18px | 24px | 600 |
| `body` | IBM Plex Sans | 14px | 20px | 400 |
| `secondary` | IBM Plex Sans | 13px | 18px | 400 |
| `label-mono` | JetBrains Mono | 13px | 16px | 500 |
| `technical-metadata` | IBM Plex Mono | 12px | 16px | 400 |

Additional sizes used in the screen:

| Context | Family | Size | Weight |
|---|---|---|---|
| District overlay label | IBM Plex Sans | 18px | 700 |
| Panel section headings | IBM Plex Sans | 14px | 700 |
| Cell ID in detail panel | JetBrains Mono | 16px | 700 |
| Candidate cell ID (list) | JetBrains Mono | 14px | 600 (selected) / 400 |
| Score value (list) | IBM Plex Sans | 14px | 700 (selected) / 600 |
| Brand sub-label | JetBrains Mono | 10px | 400 |
| Map legend header | IBM Plex Sans | 12px | 700 |
| Count badge | JetBrains Mono | 11px | 400 |
| Level badge | IBM Plex Sans | 10px | 400 |
| Satellite band badge | JetBrains Mono | 10px | 400 |

**Google Fonts import string:**
```
IBM Plex Sans:wght@400;500;600;700
IBM Plex Mono
JetBrains Mono:wght@400;500
Material Symbols Outlined:wght,FILL@100..700,0..1
```

---

## 9. Spacing & Border-Radius Tokens

### Spacing

| Token | Value |
|---|---|
| `sidebar-width` | 216px |
| `topbar-height` | 60px |
| `list-panel-width` | 250px |
| `detail-panel-width` | 340px |
| `gutter` | 16px |
| `margin-page` | 24px |

### Border radius

| Token | CSS value | Pixels |
|---|---|---|
| `DEFAULT` | `0.125rem` | 2px |
| `lg` | `0.25rem` | 4px |
| `xl` | `0.5rem` | 8px |
| `full` | `0.75rem` | 12px |

Standard components (buttons, inputs, cards, overlays, legends): 8px (`xl`).
Progress bar tracks: 9999px (pill).
Satellite preview frame: 4px (`lg`).
Small badges: 2px.

---

## 10. Scrollbar

```css
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #f1f1f1; }
::-webkit-scrollbar-thumb { background: #CBD2D8; }
::-webkit-scrollbar-thumb:hover { background: #74777d; }
```

---

## 11. Responsive Behaviour

| Breakpoint | Behaviour |
|---|---|
| >= 1200px | Full 4-column layout (sidebar + list + map + detail) |
| 900–1199px | Reduce sidebar width; collapse candidate list if needed; keep map dominant |
| < 900px | Sidebar becomes drawer; candidate details become bottom sheet; map stays usable |

The interface must **not** switch to a mobile-style layout at normal laptop widths (>= 900px).

---

## 12. Material Symbols — Icon Reference

| Icon token | Usage |
|---|---|
| `dashboard` | Genel Bakış nav |
| `location_city` | İlçe Analizi nav |
| `menu_book` | Kütüphaneler nav |
| `location_on` | Aday Bölgeler nav (active) |
| `satellite_alt` | Uydu Görüntüleri nav |
| `science` | Metodoloji nav |
| `search` | Top bar search field |
| `help` | Top bar methodology / help link |
| `add` | Map zoom-in |
| `remove` | Map zoom-out |
| `layers` | Map layer toggle |
| `my_location` | Map locate button |
| `close` | Detail panel close |
| `assignment_late` | İnceleme durumu status icon (FILL=1) |

Removed from previous version: `notifications`, `settings` — these elements are not part of this interface.

---

## 13. District Selector — Aday Bölgeler Page Rule

The district selector on the **Aday Bölgeler** page must be populated with the unique set of `candidate.ilce` values present in `response.aday_bolgeler`.

```js
// Correct
const ilceler = [...new Set(response.aday_bolgeler.map(c => c.ilce))].sort();
```

This ensures only districts that have candidate-area analyses are shown. Do **not** hard-code district names. Do **not** populate this selector from `GET /api/ilceler` (which returns all 39 districts regardless of whether analyses exist).

`GET /api/ilceler` may be used for other non-candidate selectors elsewhere in the application (e.g. İlçe Analizi page).

---

## 14. What This Design Does NOT Include

The following must **never** be added:

- `/api/candidates` or `/api/districts` — these endpoints do not exist
- Flat field names: `hizmet_ihtiyaci_sirasi`, `hizmet_ihtiyaci_puani`, `hizmet_ihtiyaci_seviyesi`, `yer_inceleme_durumu` — use nested paths instead
- Treating `response` itself as the candidate array — use `response.aday_bolgeler`
- Treating `response` itself as the satellite array — use `response.uydu_goruntuleri`
- Geometry field named `geometry`, `geojson`, or `feature` — the real field is `candidate.geometri`
- Hard-coded district names in any dropdown
- Profile block, avatar, user name, user role label
- Notifications button or centre
- Settings button
- Report generation button ("DETAYLI ANALİZ RAPORU" or any equivalent)
- GeoTIFF or data export
- Final site recommendation or approval button
- Time-series analysis controls
- Library capacity indicators
- Accessibility scores
- Live synchronisation controls
- Any mobile-optimised layout at >= 900px
- A combined suitability score merging `candidate.hizmet_ihtiyaci.puan` and `candidate.yer_inceleme.durum`
- Invented cell IDs, scores, distances, dates, parcel numbers, or approval states
- Fabricated or placeholder satellite images (use the placeholder text instead)
- The text "İstanbul Belediyesi" — use "Kentsel Karar Destek Platformu" instead

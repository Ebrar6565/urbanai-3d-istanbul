# UrbanAI 3D İstanbul Workspace - Visual Design System

## 1. Core Visual Language

### Color Palette & Reusable Color Tokens
The palette is anchored in a deep, institutional "Midnight Navy" for primary navigation, with a "Soft Off-White" background.
- **Brand Colors:**
  - `primary`: `#000000` (Midnight Navy influence for high contrast)
  - `on-primary`: `#ffffff`
  - `primary-container`: `#0d1c32` (Deep Institutional Navy)
  - `on-primary-container`: `#76849f`
  - `secondary`: `#4059aa` (Bosphorus Blue)
  - `on-secondary`: `#ffffff`
- **Surface Colors (Tonal Layers):**
  - `background`: `#f7f9fb` (Soft Off-White)
  - `surface`: `#f7f9fb`
  - `surface-container-lowest`: `#ffffff`
  - `surface-container-low`: `#f2f4f6`
  - `surface-container`: `#eceef0`
  - `surface-container-high`: `#e6e8ea`
  - `surface-container-highest`: `#e0e3e5`
- **Text & UI Elements:**
  - `on-surface`: `#191c1e` (Dark Slate)
  - `on-surface-variant`: `#44474d`
  - `outline`: `#75777e` (1px solid borders)
  - `outline-variant`: `#c5c6cd`
- **Functional Accents:**
  - `error`: `#ba1a1a` (Amber/Red warnings)
  - `on-error`: `#ffffff`
  - Teal/Green: Reserved for verified municipal data or active map layers.

### Typography Hierarchy (IBM Plex Sans)
Typography conveys a systematic, engineering-led aesthetic.
- **display-lg:** 32px, Semi-Bold (600), Line Height: 40px, Tracking: -0.02em
- **headline-md:** 24px, Semi-Bold (600), Line Height: 32px
- **title-sm:** 18px, Medium (500), Line Height: 24px
- **body-md:** 15px, Regular (400), Line Height: 22px (Optimized for high-density information)
- **body-sm:** 13px, Regular (400), Line Height: 18px
- **label-caps:** 11px, Semi-Bold (600), Line Height: 16px, Tracking: 0.08em (Category headers)
- **mono-data:** IBM Plex Mono, 12px, Regular (450), Line Height: 16px (Coordinate readouts, parcel IDs)

### Spacing System
Based on a 4px baseline grid for micro-precision.
- `unit`: 4px
- `gutter`: 16px
- `container_padding`: 24px
- `sidebar_width`: 320px
- `toolbar_width`: 64px

### Shapes & Corner Radii
- **Standard Components:** Soft 4px radius (`0.25rem`) for buttons, inputs, and tooltips.
- **Large Containers:** Sharp corners (0px) where they meet the browser edge (e.g., sidebars).
- **Circular Shapes:** Strictly avoided, except for specific map markers.

### Elevation & Depth
- **No Heavy Shadows:** Depth is communicated through color-blocking and fine lines.
- **Strict Outlines:** 1px solid strokes (`outline-variant`) define panel boundaries.
- **Active States:** Subtle sharp shadow (`0px 2px 4px rgba(10, 25, 47, 0.1)`) for floating modals.

---

## 2. Layout & Shell Structure

### Desktop Application Shell
A fixed-fluid hybrid model designed for a workspace environment, maximizing the map area. Uses a "Pale Stone" surface with a 1px "Dark Slate" border for panels.

### Top Application Bar
Slim and minimal. Primarily houses the workspace title, global search (if not in sidebar), and user profile. Usually integrated smoothly with the left navigation or floating above the map.

### Left Navigation Structure
- **Fixed Width:** 320px
- **Content:** Layer controls, data filters, and category headers (`label-caps`).
- **Styling:** "Checkbox + Label + Toggle" pattern. Active layers are highlighted with a subtle Teal left-border stripe (3px).

### Map-First Workspace Layouts
The central area is a fluid 3D viewport. The background map sits on the lowest visual layer. UI elements feel like precision instruments overlaid on a digital twin of the city.

### Side Detail Panels
- **Collapsible Right-Hand Panel:** Used for detailed property inspection or analytical charts.
- **Styling (Cards/Inspectors):** Flat surfaces with no shadow. Hairline horizontal dividers separate property titles from data attributes.

### Satellite Imagery Workspace
- A specialized layout focusing on remote sensing data. 
- Emphasizes the map viewport, potentially hiding or collapsing sidebars to maximize imagery analysis.

### Methodology Page Structure
- **Text-Heavy Layout:** Uses `body-md` (15px) for long-form reports.
- **Alignment:** Centralized, constrained width for readability. Structured with clear headings (`headline-md`, `title-sm`).

---

## 3. UI Components

### Data Tables
- **High-Density:** Zebra-striped with "Pale Stone" (`surface-container-low`) and "White" (`surface-container-lowest`).
- **Dividers:** 1px vertical dividers for precise column alignment.
- **Typography:** Uses `mono-data` for numeric values to ensure character alignment.

### Search and Filter Controls
- **Input Fields:** Rectangular with a Soft (4px) radius. 1px Slate border that darkens to Midnight Navy (`primary-container`) on focus.

### Buttons and Links
- **Primary Buttons:** Midnight Navy background with White text, 4px radius.
- **Secondary/Ghost Buttons:** Transparent with a 1px Slate border, used for secondary map tools.

### Status Badges
- Small, uppercase labels.
- **Green:** Verified municipal data.
- **Amber/Red:** Warnings and critical infrastructure alerts (used sparingly).

### Map Legends
Floating panels, avoiding heavy shadows. Uses 1px solid borders. Positioned unobtrusively, often utilizing `mono-data` and `body-sm` for legibility.

### Coordinate Display
A small, semi-transparent dark bar (Midnight Navy at 80% opacity) anchored to the bottom right of the viewport, using the `mono-data` typography.

---

## 4. UI States & Adaptations

### Loading States
- Subtle, technical skeleton loaders or linear progress bars matching the Midnight Navy/Teal palette. Avoid playful or bouncy animations.

### Empty States
- Minimalist text (`body-md`) and perhaps a simple wireframe icon. Placed centrally in the data panels or tables.

### Error States
- Restrained use of the `error` color (`#ba1a1a`). Clear, actionable error messages formatted in `IBM Plex Sans`.

### Tablet and Mobile Adaptation Rules
- **Sidebars:** Transform into bottom sheets or overlay drawers to preserve maximum viewport area for the map.

---

## 5. Unsupported Prototype Elements

The Stitch prototype contains narrative or static elements that **must not** be implemented in the final dynamic application. Real values must come exclusively from the existing FastAPI endpoints.

**Inaccurate or Unsupported Elements to Exclude:**
- Invented fixed dates
- Invented library or district values
- Satellite time-series features
- Raw GeoTIFF download
- Live automatic synchronization
- Library open/closed status
- Library capacity
- Accessibility score
- Final site recommendation
- Any combined suitability score

**Critical System Constraint:**
The actual system must maintain strict separation between these two analytical axes:
1. **Hizmet ihtiyacı** (Service Need)
2. **Yer inceleme durumu** (Site Inspection Status)

These must never be combined into a single suitability score.

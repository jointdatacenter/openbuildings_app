# Overture Buildings Explorer

Streamlit app for exploring building footprints from the [Overture Maps Buildings dataset](https://docs.overturemaps.org/guides/buildings/).

## Features

- Upload GeoJSON files to define areas of interest
- Fetch and visualize building footprints from Overture Maps
- Display comprehensive building attributes (height, floors, materials, classification)
- View ArcGIS World Imagery with building overlays
- Export building data as GeoJSON
- No authentication required - freely accessible data

## Installation

Install dependencies using uv:

```bash
uv sync
```

No API keys or authentication required!

## Running the App

Start the Streamlit app:

```bash
uv run streamlit run main.py
```

The app will open in your browser at `http://localhost:8501`.

## Usage

1. Upload a GeoJSON file containing your area of interest
2. Select a feature from the dropdown
3. Click "Fetch Overture Buildings" to retrieve building footprints
4. View building count and comprehensive attributes
5. Download results as GeoJSON

## About Overture Buildings Data

Overture Maps provides comprehensive building data with two feature types:
- **building**: Outermost footprint/roofprint with `has_parts` attribute
- **building_part**: Individual sections linked to parent buildings

### Data Sources

The dataset is a conflation of multiple sources, prioritizing community-contributed data:
1. OpenStreetMap (~660M buildings)
2. Esri Community Maps (~17.4M)
3. ML-derived datasets (Microsoft, Google)

### Available Attributes

- **Physical**: height, min_height, num_floors, num_floors_underground
- **Appearance**: facade_color, facade_material, roof_material, roof_shape, roof_color
- **Classification**: class, subtype, has_parts
- **Metadata**: id, version, sources, bbox

### Data Access

This application uses the Overture Maps Python SDK to query building data:
- **Method**: Direct S3 queries via Overture Python SDK
- **Speed**: 2-10 minutes depending on area size (first query downloads data)
- **Authentication**: None required - freely accessible
- **Source Data**: Overture Maps Foundation release 2025-10-22.0
- **Coverage**: Global (2.3 billion buildings)

### Licensing

Overture Maps data is released under **ODbL** (Open Database License), compatible with CC BY 4.0.

## References

- [Overture Maps Buildings Documentation](https://docs.overturemaps.org/guides/buildings/)
- [Overture Maps Website](https://overturemaps.org/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [DuckDB Spatial Extension](https://duckdb.org/docs/extensions/spatial.html)
# Open Buildings Explorer

Streamlit app for exploring building footprints from the [Google Earth Engine Open Buildings dataset](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings_v3).

## Features

- Upload GeoJSON files to define areas of interest
- Fetch and visualize building footprints from Google Earth Engine
- Display confidence scores and building counts
- View ArcGIS World Imagery with building overlays
- Export building data as GeoJSON

## Installation

Install dependencies using uv:

```bash
uv sync
```

## Google Earth Engine Configuration

This application queries building footprints from the Google Earth Engine Open Buildings dataset. You need to authenticate with Google Earth Engine:

### Option 1: Interactive Authentication (Local Development)

Run the authentication script once to generate persistent credentials:

```bash
uv run authenticate_gee.py
```

This will open a browser window for you to sign in with your Google account. After authentication, credentials will be saved for future use.

### Option 2: Service Account (Non-interactive/Production)

Set the following environment variables:

```bash
export EE_SERVICE_ACCOUNT="service-account@project.iam.gserviceaccount.com"
export EE_PRIVATE_KEY="$(cat service-account-key.json)"
```

## Running the App

Start the Streamlit app:

```bash
uv run streamlit run main.py
```

The app will open in your browser at `http://localhost:8501`.

## Usage

1. Upload a GeoJSON file containing your area of interest
2. Select a feature from the dropdown
3. Click "Fetch GOB Data" to retrieve building footprints
4. View building count and average confidence score
5. Download results as GeoJSON

## References

- [Streamlit GCS Tutorial](https://docs.streamlit.io/develop/tutorials/databases/gcs)
- [Google's S2 Geometry](https://blog.christianperone.com/2015/08/googles-s2-geometry-on-the-sphere-cells-and-hilbert-curve/)
- [Open Buildings Examples](https://open.gishub.org/open-buildings/examples/download_buildings/)
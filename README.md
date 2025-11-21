# Building Extractor from Satellite Imagery

This application uses AI-powered segmentation (SAM2 - Segment Anything Model 2) to automatically extract building footprints from satellite imagery. Unlike traditional methods that rely on pre-existing building databases, this app analyzes real-time satellite images to detect and extract buildings.

## Features

- **AI-Powered Building Detection**: Uses Meta's Segment Anything Model 2 (SAM2) for accurate building segmentation
- **No Pre-existing Data Required**: Extracts buildings directly from satellite imagery - no API dependencies
- **Interactive Map Interface**: Navigate to any location worldwide and extract buildings on-demand
- **Customizable Parameters**: Adjust imagery zoom level and building size filters
- **GeoJSON Export**: Download extracted building footprints in standard GeoJSON format
- **Imagery Metadata**: View satellite imagery acquisition dates for your area of interest

## How It Works

1. **Navigate**: Use the interactive map to find your area of interest
2. **Zoom**: Zoom in to at least level 17 for optimal building detection
3. **Extract**: Click the "Extract Buildings" button to analyze the current view
4. **Download**: Export the results as GeoJSON for use in GIS applications

## Technical Details

### Building Extraction Pipeline

1. **Satellite Imagery Download**: Downloads high-resolution imagery (Esri World Imagery) for the selected area
2. **AI Segmentation**: Uses SAM2 (sam2-hiera-large model) to automatically detect all objects
3. **Building Filtering**: Filters detected objects by size to identify buildings
4. **Vectorization**: Converts raster masks to vector polygons
5. **GeoJSON Export**: Provides results in standard GeoJSON format

### Model Parameters

- **Points per side**: 32 (controls detection density)
- **IoU Threshold**: 0.86 (intersection over union for quality control)
- **Stability Score**: 0.92 (ensures stable predictions)
- **Min Region Area**: 100 pixels (filters out small artifacts)

### Size Filtering

- **Minimum Building Area**: 10 m² (default, adjustable)
- **Maximum Building Area**: 10,000 m² (default, adjustable)

These parameters help distinguish actual buildings from other objects like vehicles or vegetation.

## Installation

### Requirements

- Python 3.10+
- Poetry (for dependency management)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd openbuildings_app
```

2. Install dependencies using Poetry:
```bash
poetry install
```

Or using pip:
```bash
pip install -r requirements.txt
```

### Dependencies

Key libraries used:
- `segment-geospatial`: SAM2 model for geospatial segmentation
- `leafmap`: Satellite imagery download and processing
- `streamlit`: Web application framework
- `folium`: Interactive mapping
- `geopandas`: Geospatial data handling
- `torch`: Deep learning backend

## Usage

### Running the Application

```bash
streamlit run main.py
```

The application will open in your default web browser at `http://localhost:8501`

### Workflow

1. **Navigate to Location**:
   - Use the map controls to pan and zoom to your area of interest
   - Or enter coordinates in the sidebar

2. **Adjust Settings**:
   - Set imagery zoom level (17-20, higher = more detail)
   - Configure minimum building area filter
   - Configure maximum building area filter

3. **Extract Buildings**:
   - Click "Extract Buildings" button
   - Wait for processing (may take 1-3 minutes depending on area size)
   - View extracted buildings highlighted on the map

4. **Export Results**:
   - Download GeoJSON file from the sidebar
   - Import into QGIS, ArcGIS, or other GIS software

## Performance Considerations

- **Processing Time**: 1-3 minutes per extraction (depends on area size and zoom level)
- **Area Coverage**: Best results with small to medium areas (city blocks)
- **Zoom Level**: Level 19 recommended for balance of detail and speed
- **Memory Usage**: Runs on CPU by default (GPU acceleration optional)

## Comparison with Previous Version

This version differs from the original "Open Buildings Explorer" in several key ways:

### Old Approach (Google Open Buildings)
- ✅ Pre-computed building data
- ✅ Very fast queries
- ❌ Limited geographic coverage
- ❌ Data may be outdated
- ❌ Requires GeoJSON upload
- ❌ Dependent on external API

### New Approach (SAM2 Extraction)
- ✅ Works anywhere in the world
- ✅ Uses latest satellite imagery
- ✅ No external API dependencies
- ✅ Direct map interaction (no file upload)
- ❌ Slower processing (2-3 minutes)
- ❌ Requires more computational resources

## Technical Architecture

```
User Interface (Streamlit)
    ↓
Map Interaction (Folium)
    ↓
Satellite Imagery Download (Leafmap)
    ↓
Building Detection (SAM2)
    ↓
Post-processing (GeoPandas)
    ↓
GeoJSON Export
```

## Limitations

- **Processing Speed**: Slower than database queries (2-3 minutes per extraction)
- **Area Size**: Large areas may exceed memory limits
- **Object Confusion**: May occasionally detect non-building objects (reduced by size filtering)
- **Imagery Quality**: Results depend on satellite image quality and resolution
- **Weather**: Clouds, shadows, or poor lighting may affect accuracy

## Future Enhancements

- [ ] Batch processing for multiple locations
- [ ] Building classification (residential, commercial, industrial)
- [ ] Change detection (compare different time periods)
- [ ] GPU acceleration for faster processing
- [ ] Building height estimation
- [ ] Integration with other AI models for improved accuracy

## References

- [Segment-Geospatial GitHub](https://github.com/opengeos/segment-geospatial)
- [SAM2 Paper - Meta AI](https://ai.meta.com/sam2/)
- [Leafmap Documentation](https://leafmap.org/)
- [Streamlit Documentation](https://docs.streamlit.io/)

## Original Project

This is an enhanced version of the [Open Buildings Explorer](https://github.com/jointdatacenter/openbuildings_app) project. The original version used Google Open Buildings dataset for building queries.

## License

[Specify your license here]

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
